from pyuvdata import UVData, utils as uvutils
import numpy as np
import argparse
import glob
import os
import sys
import hera_cal as hc
import copy


ap = argparse.ArgumentParser(description='Match model vis to data file, and write model and its residual.')

ap.add_argument("filename", type=str, help="Filename to image")
ap.add_argument("model_vis", type=str, help="glob-parseable path to model visibilities")
ap.add_argument("outdir", type=str, help="Output directory to write model file to")

if __name__ == "__main__":

    # parse args
    a = ap.parse_args()

    # load filename metadata
    uvd = UVData()
    uvd.read(a.filename, read_data=True)
    lst_bounds = [uvd.lst_array.min(), uvd.lst_array.max()]
    if lst_bounds[1] < lst_bounds[0]:
        lst_bounds[1] += 2*np.pi

    # get model visibilities
    if a.model_vis is None:
        sys.exit(0)
    a.model_vis = a.model_vis.strip("'")  # somtimes it has extra quotes
    mfiles = sorted(glob.glob(a.model_vis))
    if len(mfiles) == 0:
        sys.exit(0)

    # get metadata
    mfile_lsts = []
    for mf in mfiles:
        uvm = UVData()
        uvm.read(mf, read_data=False)
        mfile_lsts.append([uvm.lst_array.min(), uvm.lst_array.max()])
    mfile_lsts = np.unwrap(mfile_lsts, axis=0)
    if mfile_lsts[0, 1] < mfile_lsts[0, 0]:
        mfile_lsts[:, 1] += 2*np.pi
    if mfile_lsts.min() > lst_bounds[1]:
        mfile_lsts -= 2*np.pi

    # get files that overlap filename
    model_files = []
    for i, mf_lst in enumerate(mfile_lsts):
        if mf_lst[1] > lst_bounds[0] and mf_lst[0] < lst_bounds[1]:
            model_files.append(mfiles[i])
    if len(model_files) == 0:
        sys.exit(0)

    # load model
    uvm = UVData()
    uvm.read(model_files)

    # down select on lsts
    uvm_lsts = np.unwrap(np.unique(uvm.lst_array))
    tinds = (uvm_lsts >= lst_bounds[0]) & (uvm_lsts <= lst_bounds[1])
    uvm.select(times=np.unique(uvm.time_array)[tinds])

    # expand to data baselines
    data_bls = uvd.get_antpairpols()
    data_antpos, data_ants = uvd.get_ENU_antpos()
    data_antpos_dict = dict(zip(data_ants, data_antpos))
    model_bls = uvm.get_antpairpols()
    model_antpos, model_ants = uvm.get_ENU_antpos()
    model_antpos_dict = dict(zip(model_ants, model_antpos))
    _, _, d2m = hc.abscal.match_baselines(data_bls, model_bls, data_antpos_dict, model_antpos_dict,
                                          model_is_redundant=True)

    # construct model and residual
    mod, res = copy.deepcopy(uvd), copy.deepcopy(uvd)
    for blp in data_bls:
        # get indices in data
        bltinds = mod.antpair2ind(blp)
        pol_int = uvutils.polstr2num(blp[2], x_orientation=mod.x_orientation)
        polind = mod.polarization_array.tolist().index(pol_int)
        # if blp in d2m fill it, otherwise flag it
        if blp in d2m:
            mblp = d2m[blp]
            mod.data_array[bltinds, 0, :, polind] = uvm.get_data(mblp)
            res.data_array[bltinds, 0, :, polind] -= uvm.get_data(mblp)
        else:
            mod.flag_array[bltinds, 0, :, polind] = True
            res.flag_array[bltinds, 0, :, polind] = True

    # phase the data
    mod.phase_to_time(np.median(mod.time_array))
    res.phase_to_time(np.median(res.time_array))

    # write uvfits to outdir
    outname = os.path.basename(a.filename).replace('uvh5', 'model.uvfits')
    mod.write_uvfits(os.path.join(a.outdir, outname), spoof_nonessential=True)
    outname = os.path.basename(a.filename).replace('uvh5', 'res.uvfits')
    res.write_uvfits(os.path.join(a.outdir, outname), spoof_nonessential=True)