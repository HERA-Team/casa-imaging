from pyuvdata import UVData, utils as uvutils
import numpy as np
import argparse
import glob
import os
import sys
from hera_cal.io import HERAData, partial_time_io
from hera_cal.abscal import get_all_times_and_lsts, get_d2m_time_map, match_times, match_baselines
import copy

ap = argparse.ArgumentParser(description='Match model vis to data file, and write model and its residual.')

ap.add_argument("filename", type=str, help="Filename to image")
ap.add_argument("model_vis", type=str, help="glob-parseable path to model visibilities in uvh5 format")
ap.add_argument("outdir", type=str, help="Output directory to write model file to")
ap.add_argument("--model_not_redundant", default=False, action="store_true", help="model_vis files contain all baselines, not just unique ones")

if __name__ == "__main__":

    # parse args
    a = ap.parse_args()

    # get model visibilitity file list
    if a.model_vis is None:
        sys.exit(0)
    a.model_vis = a.model_vis.strip("'")  # somtimes it has extra quotes
    mfiles = sorted(glob.glob(a.model_vis))
    if len(mfiles) == 0:
        sys.exit(0)

    # get lst-matched model files from mfiles
    matched_model_files = sorted(set(match_times(a.filename, mfiles, filetype='uvh5')))
    if len(matched_model_files) == 0:
        sys.exit(0)

    # load data and model metadata
    hd = HERAData(a.filename)
    hdm = HERAData(matched_model_files)

    # get model bls and antpos to use later in baseline matching
    model_bls = hdm.bls
    model_antpos = hdm.antpos
    if len(matched_model_files) > 1:  # in this case, it's a dictionary
        model_bls = list(set([bl for bls in list(hdm.bls.values()) for bl in bls]))
        model_antpos = {ant: pos for antpos in hdm.antpos.values() for ant, pos in antpos.items()}

    # get corresponding times in the data and model
    all_data_times, all_data_lsts = get_all_times_and_lsts(hd, unwrap=True)
    all_model_times, all_model_lsts = get_all_times_and_lsts(hdm, unwrap=True)
    d2m_time_map = get_d2m_time_map(all_data_times, all_data_lsts, all_model_times, all_model_lsts, extrap_limit=.5)

    # get matching baselines in the data and model
    (data_bl_to_load,
     model_bl_to_load,
     data_to_model_bl_map) = match_baselines(hd.bls, model_bls, hd.antpos, model_antpos=model_antpos, tol=1.0,
                                             data_is_redsol=False, model_is_redundant=(not a.model_not_redundant))

    # load model (just the times of interest)
    model_times_to_load = [d2m_time_map[time] for time in hd.times]
    model, _, _ = partial_time_io(hdm, np.unique(model_times_to_load), bls=model_bl_to_load)

    # update data to make model or residual, then write to disk
    for out in ['model', 'res']:
        hd = HERAData(a.filename)
        data, _, _ = hd.read(bls=data_bl_to_load)
        for bl in data:
            if out == 'model':
                data[bl] = model[data_to_model_bl_map[bl]]
            elif out == 'res':
                data[bl] -= model[data_to_model_bl_map[bl]]
        hd.update(data=data)
        hd.phase_to_time(np.median(hd.time_array))
        outname = os.path.basename(filename).replace('uvh5', f'{out}.uvfits')
        hd.write_uvfits(os.path.join(.outdir, outname), spoof_nonessential=True)
