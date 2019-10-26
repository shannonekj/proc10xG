"""
Copyright 2019 Matt Settles
Created June 8, 2017
Updated October 18, 2019

Process raw data reads generated by 10x,
identify and extract the gem barcode, compare it to a white list
and then strip off the random priming region. Attach all the sequence
data to the end of the read ids
"""
import argparse
import sys
import os
import time
import traceback

from .illumina_10X_reads import TwoRead10xLLRun
from .illumina_10X_reads import TwoRead10xLLOutput
from .barcodes_10xG import barcodes_10xG
from .misc import median

# complete refactoring to python3 and application module
process_10xReads_version_num = "0.1.0"

def process_10xReads_ARGS():
    """
    generate parser
    """
    p10xR_parser = argparse.ArgumentParser(
            description='process_10xReads.py, to process raw fastq files extracting gem barcodes and comparing to a white list',
            epilog='For questions or comments, please contact Matt Settles <settles@ucdavis.edu>\n%(prog)s version: ' + process_10xReads_version_num, add_help=True)
    p10xR_parser.add_argument('--version', action='version', version="%(prog)s version: " + process_10xReads_version_num)

    p10xR_parser.add_argument('--quiet', help="turn off verbose output",
                        action="store_false", dest="verbose", default=True)

    p10xR_group = p10xR_parser.add_argument_group("Inputs", "10x fastq files to input (can be gz).")

    p10xR_group.add_argument('-1', '--read1', metavar="read1", dest='read1', help='read1 of a pair, multiple files can be specified separated by comma',
                       action='store', type=str, nargs='+')

    p10xR_group.add_argument('-2', '--read2', metavar="read2", dest='read2', help='read2 of a pair, multiple files can be specified separated by comma',
                       action='store', type=str, nargs='+')

    p10xR_group2 = p10xR_parser.add_argument_group("Output", "10x fastq files to output options.")

    p10xR_group2.add_argument('-o', '--output', help="Directory + prefix to output reads, [default: %(default)s]",
                        action="store", type=str, dest="output_dir", default="stdout")

    p10xR_group2.add_argument('-g', '--nogzip', help="do not gzip the output, ignored if output is stdout",
                        action="store_true", dest="nogzip", default=False)

    p10xR_group2.add_argument('-i', help="output in interleaved format, if -o stdout, interleaved will be chosen automatically [default: %(default)s]",
                        action="store_true", dest="interleaved", default=False)

    p10xR_group3 = p10xR_parser.add_argument_group("Application", "Application specific options.")

    p10xR_group3.add_argument('-b', '--bctrim', help='trim gem barcode [default: %(default)s]',
                        type=int, dest="bctrim", default=16)

    p10xR_group3.add_argument('-t', '--trim', help="trim addional primer bases after the gem barcode [default: %(default)s]",
                        type=int, dest="trim", default=7)

    p10xR_group3.add_argument('-a', '--all', help="output all reads, not just those with valid gem barcode, STATUS will be UNKNOWN, or AMBIGUOUS [default: %(default)s]",
                        action="store_true", dest="output_all", default=False)

    p10xR_group3.add_argument('-w', '--whitelist', help="gem barcode whitelist file to use [default: %(default)s]",
                        action='store', type=str, dest="whitelist", default="4M-with-alts-february-2016.txt")

    options = p10xR_parser.parse_args()

    if options.read1 is None:
        sys.stderr.write("ERROR[process_10xReads]\tRead file 1 is missing\n")
        sys.exit(1)
    if options.read2 is None:
        sys.stderr.write("ERROR[process_10xReads]\tRead file 2 is missing\n")
        sys.exit(1)

    file_path = os.path.dirname(os.path.realpath(__file__))
    if os.path.isfile(options.whitelist):
        whitelist = options.whitelist
    elif os.path.isfile(os.path.join(file_path, '../data/barcodes/' + options.whitelist)):
        whitelist = os.path.join(file_path, '../data/barcodes/' + options.whitelist)
    else:
        sys.stderr.write("ERROR[process_10xReads]\tBarcode whitelist file not accessible.\n")
        sys.exit(1)

    process_10xReads_EXE(options.read1,
                         options.read2,
                         options.output_dir,
                         options.interleaved,
                         options.nogzip,
                         whitelist,
                         options.bctrim,
                         options.trim,
                         options.output_all,
                         options.verbose)

    sys.exit(0)


def process_10xReads_EXE(read1, read2, output_dir, interleaved, nogzip, whitelist, bctrim, trim, output_all, verbose):

    stime = time.time()

    output_list = ["MATCH", "MISMATCH1"]
    if output_all:
        output_list.extend(["AMBIGUOUS", "UNKNOWN"])
    # open output files
    output = TwoRead10xLLOutput(output_dir, nogzip, interleaved, output_list, verbose)

    # Process read inputs:
    iterator = TwoRead10xLLRun(read1, read2, bctrim, trim, verbose)

    # Lead the whitelist:
    whitelistDB = barcodes_10xG(whitelist,  bctrim, verbose)

    try:
        while 1:
            fragment = iterator.next_raw(whitelistDB, 250000)
            if len(fragment) == 0:
                    break
            output.writeProcessedRead(fragment)
            if verbose:
                sys.stderr.write("PROCESS\tREADS\treads analyzed:{}|reads/sec:{:.0f}|barcodes:{}|median_reads/barcode:{:.2f}\n".format(
                                 iterator.count(),
                                 iterator.count() / (time.time() - stime),
                                 whitelistDB.get_gbcCounter_size(),
                                 median(list(whitelistDB.get_gbcCounter_items()))))
        whitelistDB.print_gbcCounter(output_dir)
        output.close()

        if verbose:
            sys.stderr.write("PROCESS\tREADS\treads analyzed:{}|reads/sec:{:.0f}|barcodes:{}|median_reads/barcode:{:.2f}\n".format(
                             iterator.count(),
                             iterator.count() / (time.time() - stime),
                             whitelistDB.get_gbcCounter_size(),
                             median(list(whitelistDB.get_gbcCounter_items()))))
            sys.stderr.write("PROCESS\tBARCODE\tMATCH: {} ({:.2f}%%)\n".format(
                             whitelistDB.statusCounter["MATCH"], (float(whitelistDB.statusCounter["MATCH"]) / iterator.count()) * 100))
            sys.stderr.write("PROCESS\tBARCODE\tMISMATCH1: {} ({:.2f}%%)\n".format(
                             whitelistDB.statusCounter["MISMATCH1"], (float(whitelistDB.statusCounter["MISMATCH1"]) / iterator.count()) * 100))
            sys.stderr.write("PROCESS\tBARCODE\tAMBIGUOUS: {} ({:.2f}%%)\n".format(
                             whitelistDB.statusCounter["AMBIGUOUS"], (float(whitelistDB.statusCounter["AMBIGUOUS"]) / iterator.count()) * 100))
            sys.stderr.write("PROCESS\tBARCODE\tUNKNOWN: {} ({:.2f}%%)\n".format(
                             whitelistDB.statusCounter["UNKNOWN"], (float(whitelistDB.statusCounter["UNKNOWN"]) / iterator.count()) * 100))
    except (KeyboardInterrupt, SystemExit):
        sys.exit("ERROR[process_10xReads]\t{} unexpectedly terminated\n".format(__name__))
    except Exception:
        sys.stderr.write("".join(traceback.format_exception(*sys.exc_info())))
        sys.exit("ERROR[process_10xReads]\tAn unknown fatal error was encountered.\n")
