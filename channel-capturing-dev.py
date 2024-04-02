# -*- coding: utf-8 -*-
"""
Created on Fri Nov 11 10:45:48 2022

@author: jng22


Capture channel activity by measuring and monitoring the iq power in different frequency bands using BB60C. Configure the BB60C with input parameters and perform the IQ acquisition and processing.

Input : configuration json file(optional)
Output : 
    <output_filename>.csv : Event list that captures the events in the specified channels
    Metadata-<output_filename>.csv : Metadata of the Capturing. 
    (Optional) <config_name>.json : The configuration of this capturing. This will be output only if -w/--writeconfig is called
    

Bandwidth limitation table (Decimation rate, sampling rate, Max BW): 
    (1, 40 Ms/s, 27 MHz)
    (2, 20 Ms/s, 17.8 MHz)
    (4, 10 Ms/s, 8 MHz)
    (8, 5 Ms/s, 3.75 MHz)
    (16, 2.5 Ms/s, 2 MHz)
    (32, 1.25 Ms/s, 1 MHz)
    (64, 0.625 Ms/s, 0.5 MHz)
    
TODO : 
    1. Write current settings to configuration file (done)
    2. Change option "bandwidth" to "span" (done)
    3. Add the optiion threshold offset for the acquire option (done)
    4. Always output metadata file (done)
    5. Refine code, delete unused part
    6. Check distribution of random number (done)
        randrange() is producing equally distributed values. (https://docs.python.org/3/library/random.html#random.randrange)
    7. Check the unit of gain and IQ data. And check the uncertainty
    8. Add comment option to write into metadata file (done)
    9. Add more options for sweeping (done)
    10. (Future) hop with probability p if occupancy rate is over x
    11. Deal with threshold offset (done)
    12. Add the exception handling for Ctrl+C (close the device so we do not need to close the program for next time using the device) (done)
    
Test directly using runfile('channel-capturing.py', args='<your argument>')

"""
#%%  Import necessary packages
# Import the argparse library
import argparse
import os
import sys
import signal
from datetime import datetime
import json
import csv

# Import modules relate to processing
import numpy as np
import math
import random

# Timer module
import time

#### Manual setting variables #################################################

# Set the bb API directory to python search path and import the package
# https://stackoverflow.com/questions/59014318/filenotfounderror-could-not-find-module-libvlc-dll?fbclid=IwAR25hyP3R1sDf94Sk8aprcxGgEFuaZqz-Z-tV5MfZlNVDIJqNMbpfSUre2w
# DLL dependencies for extension modules and DLLs loaded with ctypes on Windows 
# are now resolved more securely after python 3.8.
API_directory=r'C:\Users\jng22\Downloads\Jing\BB60C\software-relate\signal_hound_sdk_11_15_22\signal_hound_sdk\device_apis\bb_series\examples\python\bbdevice'
os.add_dll_directory(API_directory)

# The amount of inaccurate iq data discarded on each configuration due to the filter ramp up time
garbage_size = 2048

# The occupancy threshold that create probability to keep capturing in the same frequency
occupancy_threshold = 0.3

# The probability to stay capturing in the same frequency if occupancy rate is over the threshold
p_samefreq = 0.7

###############################################################################
from bbdevice.bb_api import *

# This is the exception handler when Ctrl+C is called to interrupt the program while capturing data using BB60C. The purpose is to appropriately close the BB60C device so an error would not occur if the program is called again
def customized_exit(signum, frame) :
    # The following line is to restore the original SIGINT handler. Though it's useless in this example, it's a good practice to change the customized handler back if the customized one is no longer used.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    print("Program is interrupted by Ctrl+C. Close BB60C and exit the program")
    
    bb_close_device(handle)
    # Write event to csv file
    print("Write capture event to the output csv <{}> file".format(output_filename))
    output_path = os. getcwd() + '\\'

    # For Windows
    with open(output_path + output_filename + '.csv','w', newline='') as out:
    # for linux : with open(output_path + output_file,'w') as out:
        csv_output = csv.writer(out)
        csv_output.writerow(['Event start time','Time in Nano second', 'Center Freq (Hz)', 'Avg Power (dBm)'])
        csv_output.writerows(event_list)
        #for row in data:
        #    csv_out.writerow(row)    

    # Write Metadata file
    # For Windows
    with open(output_path + "Metadata-" + output_filename + '.csv','w', newline='') as out:
    # for linux : with open(output_path + output_file,'w') as out:
        csv_output = csv.writer(out)
        csv_output.writerow(['Sampling Rate (M/s)', fs/1e6])
        csv_output.writerow(['Sweep option', args.option])
        csv_output.writerow(['Min Center frequency (MHz)', center_freq/1e6])
        csv_output.writerow(['Max Center frequency (MHz)', center_freq/1e6 + (channel_number-1)*filter_bandwidth/1e6])
        csv_output.writerow(['Filter Bandwidth (MHz)', filter_bandwidth/1e6])
        csv_output.writerow(['Total channels sweeping during capturing', channel_number])
    #    csv_output.writerow(['Center frequency (Hz)', center_freq])
        csv_output.writerow(['Threshold (dBm)', args.threshold])
        csv_output.writerow(['Reference level (dBm)', ref_level])
        csv_output.writerow(['Total collection duration (min)', args.duration])
        csv_output.writerow(['Buffer duration/min event size (us))', args.bufferduration])
        csv_output.writerow(['Frequency dwell time (ms)', args.fcduration])
        csv_output.writerow(['Comments', args.comment[0]])
    sys.exit()


#%%  Parse the input argument
# If a configuration json file is not specified, parameters will be set first
# from the default_conf.json, and then override by the argument from command line.
# Or you can also set the parameters using --conf <configuration json file>

f_upLim = 6000.0
f_downLim = 0.0

# This is used for float argument restriction
def restricted_center_freq(in_var):
    try:
        in_var = float(in_var)
    except ValueError:
        raise argparse.ArgumentTypeError("%r not a floating-point literal" % (in_var))

    if in_var <= f_downLim or in_var >= f_upLim:
        raise argparse.ArgumentTypeError("%r not in range [%f, %f]"%(in_var, f_downLim, f_upLim))
    return in_var

def positive_float(in_var):
    try:
        in_var = float(in_var)
    except ValueError:
        raise argparse.ArgumentTypeError("%r not a floating-point literal" % (in_var))

    if in_var < 0.0:
        raise argparse.ArgumentTypeError("%r not positive"%(in_var))
    return in_var

def positive_int(in_var):
    try:
        in_var = int(in_var)
    except ValueError:
        raise argparse.ArgumentTypeError("%r not a integer literal" % (in_var))

    if in_var < 0:
        raise argparse.ArgumentTypeError("%r not positive"%(in_var))
    return in_var

# Check if the -w, --writeconfig option is called
def check_w_option(args, termination) :
    if args.writeconfig is not None:
        if args.writeconfig == []:
            output_configname = 'config-' + datetime.now().strftime("%m-%d-%y-%Hh-%Mm-%Ss") +'.json'
        else : 
            output_configname = args.writeconfig[0] + '.json'
        
        print('Write out configuration file name : {}'.format(output_configname))
        with open('default_conf.json') as conf_file:
            conf_var = json.load(conf_file)
            # Set the json file parameters
            conf_var["frequency"] = args.frequency
            conf_var["span"] = args.span
            conf_var["reference"] = args.reference
            conf_var["threshold"] = args.threshold
            conf_var["decimation"] = args.decimation
            conf_var["duration"] = args.duration
            conf_var["bufferduration"] = args.bufferduration
            conf_var["fcduration"] = args.fcduration
            conf_var["option"] = args.option
            conf_var["offset"] = args.offset
        
        format_json = json.dumps(conf_var, indent=4)
        # Writing to <output_configname>.json
        with open(output_configname, 'w') as outfile:
            outfile.write(format_json)
        
    if termination == True : 
         sys.exit()
        


#### Argparse #################################################################
# Create the parser
my_parser = argparse.ArgumentParser(prog="channel-capturing",
    description=__doc__)

# Add the arguments : https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument 
my_parser.add_argument('-o', '--output',
                       metavar='<output_filename>',
                       type=str,
                       help='Set the output file name. Default name will be py-out-<current time>')

my_parser.add_argument('--conf',
                       metavar='<configuration_file>',
                       action='append',
                       help='Configuration file for the argparse')

my_parser.add_argument('-f', '--frequency',
                       metavar='<center_freq>',
#                       required=True,
                       type=restricted_center_freq,
                       help='Start Center frequency (MHz) of the sweep measurement. Frequency should be in the range of sub-6 Ghz. Default to 2410.0 MHz')
                       
my_parser.add_argument('-s', '--span',
                       metavar='<Sweep_span>',
                       type=positive_float,
                       help='Total Sweep span (MHz) of the measurement. The real \
                           sweeping span may be different based on the filter_bandwidth. \
                           Default mode is no sweeping')

my_parser.add_argument('-fb', '--filter_bandwidth',
                       metavar='<filter_bandwidth>',
                       type=positive_float,
                       help='Bandwidth (MHz) of the iq capturing on specific center frequency. \
                           For BB60C different max bandwidth for different sample rate is specified in the bandwidth limitation table')

my_parser.add_argument('-ref', '--reference',
                       metavar='<reference_level>',
                       type=float,
                       help='Reference level (dBm) for the device. Default to -20dBm and should not set too low to prevent damaging the device')


my_parser.add_argument('-th', '--threshold',
                       metavar='<Threshold>',
                       type=float,
                       help='Threshold value (dBm) for the post processing. Only output the event having power larger than the threshold. Default to -45dBm.')
                       
my_parser.add_argument('-d', '--decimation',
                        metavar='<Fs_decimation>',
                        type=int,
                        choices=[1, 2, 4, 8, 16, 32, 64],
                        help='Decimation value for sampling frequency(can only be power of 2). The Sample frequency = 40/(decimation) Ms. Default to 8.')   
                      
my_parser.add_argument('-t', '--duration',
                       metavar='<Collection_duration>',
                       type=positive_int,
                       help='Collection duration (min). Default to ?? min.')

my_parser.add_argument('-b', '--bufferduration',
                       metavar='<Buffer_duration>',
                       type=positive_int,
                       help='The collection time to buffer for each measurement acquisition (us). Default to 50us.')

my_parser.add_argument('-ft', '--fcduration',
                       metavar='<Fc_dwelltime>',
                       type=positive_int,
                       help='The dwell time for the capturing staying in one frequency (ms). Default to 10ms.')

my_parser.add_argument('--acquire',
                       metavar='<acquire_time>',
                       nargs='*',
                       type=positive_int,
                       help='The acquire time for the threshold for the noise floor (sec). Default to 5s. If --acquire option is called, it will capture and average the IQ data in <acquire_time> and then set the acquire_threshold in default_conf.json file')

# my_parser.add_argument('-r', '--reset',
#                        action='store_true',    
#                        help='If the -r/--reset option is called, it will reset the default configuration after this execution. Currently the only reset variable is the acquire_threshold in default_conf.json file')

# my_parser.add_argument('--meta',
#                        action='store_true',    
#                        help='If --meta option is called, it will also output the Metadata file along with the event list file')

my_parser.add_argument('-w', '--writeconfig',
                       metavar='<config_filename>',
                       nargs='*',
                       type=str,
                       help='Output the current configuration to a configuration json file with name <config_filename>. Default name will be config-<current time>')

my_parser.add_argument('--offset',
                       metavar='<threshold_offset>',
                       type=positive_float,
                       help='The offset added on the acquired noise floor (dBm). This is only effective if the --acquire option is called. The threshold value written to the configuration file will be (acquired_noise_floor + threshold_offset). Default to 10dBm.')

my_parser.add_argument('--option',
                       metavar='<Sweep_option>',
                       type=str,
                       choices=['fixed', 'sweep', 'rand-sweep','hop-with-p', 'hop-ifnot-busy'],
                       help='Sweep options for frequency hopping. Default to sweep')

my_parser.add_argument('--comment',
                       metavar='"<your comments>"',
                       type=str,
                       nargs=1,
                       default=[""],
                       help='This option helps writing comments with content "<your comments>" to output Metadata file. Remember to add the double quote ("") to your comments. ')

# Execute the parse_args() method
args = my_parser.parse_args()


    
#### Load from configuration and argparse #####################################
# Check if a configuration file is specified, if not, default configuration file will be loaded
if args.conf is not None:
    with open(args.conf[0], 'r') as f:
        my_parser.set_defaults(**json.load(f))    
else:
    with open('default_conf.json', 'r') as f:
        my_parser.set_defaults(**json.load(f))


# Reload the arguments to override with command line value
args = my_parser.parse_args()

# print("Check whether option is load from configuration file. Sweep_option : {}".format(args.option))

if args.output is None:
    output_filename = 'py-out-' + datetime.now().strftime("%m-%d-%y-%Hh-%Mm-%Ss")
else:
    output_filename = args.output

MAX_BW_TABLE = { 1 : 27.0e6,
                 2 : 17.8e6, 
                 4 : 8.0e6,
                 8 : 3.75e6,
                 16 : 2.0e6,
                 32 : 1.0e6,
                 64 : 0.5e6}

# Check if filter_bandwidth is specified and effective, if not, use the default table
if args.filter_bandwidth is not None:
    # check if it's over the limit 
    filter_bandwidth = args.filter_bandwidth * 1e6
    if filter_bandwidth > MAX_BW_TABLE[args.decimation] :
        sys.exit("filter bandwidth out of limit")  
else:
    # use the bandwidth table
    filter_bandwidth = MAX_BW_TABLE[args.decimation] 

# Check and calculate the channel number based on the span bandwidth specified
if args.span != -1:
    # calculate how many channels for sweeping
    channel_number = math.ceil(args.span*1e6/filter_bandwidth)
else:
    # non sweeping mode
    channel_number = 1
if channel_number == 1 :
    args.option = 'fixed'


#### Variables summary ########################################################
# output file name : output_filename

# decimation rate : args.decimation

# sample rate (Hz)
fs = 40.0e6/args.decimation; 

# Center Freq (Hz)
center_freq = args.frequency*1.0e6;

# args.threshold (dBm) & mW_threshold (mW). 
mW_threshold = 10 ** (args.threshold/10);

# The bandwidth set for IQ capturing in one center freq : filter_bandwidth (Hz)
# Total span set : args.span(MHz)

# Total number of channel in sweep : channel_number

# Reference level for the device (dbm)
ref_level = args.reference;

# Collection duration (s)
duration = args.duration * 60;

# The collection time to buffer for each measurement acquisition (s)
bufferduration = args.bufferduration*0.000001;

# Reference The dwell time for the capturing staying in one frequency (s)
fcduration = args.fcduration*0.001;

# Number of captures in one freq
num_captures_samefreq = round(fcduration/bufferduration)

# buffer size per iq capture
buffer_size = math.ceil(fs*bufferduration)


#### Items check ##############################################################
# Check if the --acquire option is called
if args.acquire is not None:
    if args.acquire == []:
        args.acquire = [5]
    print('Value of acquired time is set to {} seconds'.format(args.acquire[0]))
    
    print('Start acquiring average IQ power with sample rate {} Ms ...'.format(40/args.decimation))
    
    # Use 0.5 second buffer size since the BB60C build-in buffer size is around 1 second amount
    acquire_rounds = args.acquire[0]/0.5 
    acquire_buffer_size = fs*0.5    
    accumulate_iq_power = 0.0
    
    # Open device
    handle = bb_open_device()["handle"]
    # Configure device (first time)
    bb_configure_ref_level(handle, ref_level)
    bb_configure_gain_atten(handle, BB_AUTO_GAIN, BB_AUTO_ATTEN)
    bb_configure_IQ_center(handle, center_freq)
    bb_configure_IQ(handle, args.decimation, filter_bandwidth)

    # Initialize
    bb_initiate(handle, BB_STREAMING, BB_STREAM_IQ)

    # Flush IQ data filter ramp up time
    garbage = bb_get_IQ_unpacked(handle, garbage_size, BB_TRUE)["iq"]

    # capture <num_captures_samefreq> round in this center frequency
    i = 0
    while (i<acquire_rounds):
        # Here the parameter should be set BB_FALSE
        acquire_iq = bb_get_IQ_unpacked(handle, int(acquire_buffer_size), BB_FALSE)["iq"]
        # Calculate the avg power using (iq * conj(iq) / total samples)
        acquire_iq_power = np.abs(np.vdot(acquire_iq, acquire_iq) / acquire_buffer_size)
        accumulate_iq_power = accumulate_iq_power + acquire_iq_power
        i = i+1

    avg_iq_power = 10 * np.log10(accumulate_iq_power/acquire_rounds)
    print("Average IQ power in {} seconds is {} dBm".format(args.acquire[0], avg_iq_power))
    
    # Remember to delete the buffer, close the device
    bb_close_device(handle)
    del acquire_iq
    
    ####### NEED FURTHER CHECK
    args.threshold = avg_iq_power + args.offset
    print("Threshold power write to output configuration file is {} dBm".format(args.threshold))
    check_w_option(args, True)
    


# Check if the -w, --writeconfig option is called
check_w_option(args, False)
    


# # Check if -r/--reset option is called
# if args.reset == True:
#     with open('default_conf.json') as conf_file:
#         conf_var = json.load(conf_file)
#         conf_var["acquire_threshold"] = 999
    
#     format_json = json.dumps(conf_var, indent=4)
#     # Writing to sample.json
#     with open('default_conf.json', 'w') as outfile:
#         outfile.write(format_json)
#         sys.exit("Finish resetting")
        
# # Debug use
# for arg in vars(args):
#     print(' {} {}'.format(arg, getattr(args, arg)))

#### Print out information ####################################################
print("#### Device Settings ####")
print("output file name : {}".format(output_filename))
print("Start center freqency : {} MHz".format(center_freq*0.000001))
print("Sample freqency : {} Ms".format(fs*0.000001))
print("Filter Bandwidth : {} MHz".format(filter_bandwidth*0.000001))
print("Reference level : {} dBm. Threshold = {}, mW_threshold = {}".format(ref_level, args.threshold, mW_threshold))
#print("Total span set : {} MHz".format(args.span))
print("Sweep option : {}".format(args.option))
print("Actual sweep from {} - {} Mhz".format(center_freq*0.000001, center_freq*0.000001 + (channel_number-1)*filter_bandwidth*0.000001))
print("Buffer size : {}. Actual buffer duration : {} us".format(buffer_size, buffer_size*1e6/fs))
print("Fc duration : {} ms. Actual Fc duration : {} ms".format(fcduration*1e3, buffer_size*num_captures_samefreq*1e3/fs))
print("Total collection time : {} min".format(duration/60))

print("I'm dev")
#sys.exit()
#%%  Open the BB60C and start the acquisition

# Start using customized exception handler
signal.signal(signal.SIGINT, customized_exit)

# Create the event list
event_list = []
current_freq = center_freq

# Open device
handle = bb_open_device()["handle"]



#### Start the first round of measurement
measure_start_time = time.perf_counter()
# Configure device (first time)
bb_configure_ref_level(handle, ref_level)
bb_configure_gain_atten(handle, BB_AUTO_GAIN, BB_AUTO_ATTEN)
bb_configure_IQ_center(handle, center_freq)
bb_configure_IQ(handle, args.decimation, filter_bandwidth)

# Initialize
bb_initiate(handle, BB_STREAMING, BB_STREAM_IQ)

# Flush IQ data filter ramp up time
garbage = bb_get_IQ_unpacked(handle, garbage_size, BB_TRUE)["iq"]

# capture <num_captures_samefreq> round in this center frequency
i = 0
print('Start capturing from frequency : {}'.format(center_freq)) #debug use
while (i<num_captures_samefreq):
    # Here the parameter should be set BB_FALSE
    iq_struct = bb_get_IQ_unpacked(handle, int(buffer_size), BB_FALSE)
    iq = iq_struct["iq"]
    iq_buffer_start_nano = iq_struct["nano"]
    iq_buffer_start_sec = iq_struct["sec"]
    
    #print("The timestamp : {}".format(capture_time))
    
    # Calculate the avg power using (iq * conj(iq) / total samples)
    avg_iq_power = np.abs(np.vdot(iq, iq) / buffer_size)
    
    # Check if it's over the threshold, if yes, add to event_list
    if (avg_iq_power >= mW_threshold) : 
        # calculate the dBm value
        avg_iq_power = 10 * np.log10(avg_iq_power)
        capture_time = datetime.fromtimestamp(iq_buffer_start_sec).strftime('%Y-%m-%d %H:%M:%S')
        event_list.append((capture_time, iq_buffer_start_nano, current_freq, avg_iq_power))
    i = i+1




#%%  Hop to other center frequency based on sweep_option if not exceed the whole collection duration
if args.option == 'fixed' :
    while (time.perf_counter() - measure_start_time) < duration :
        i = 0
        while (i<num_captures_samefreq):
            # Here the parameter should be set BB_FALSE
            iq_struct = bb_get_IQ_unpacked(handle, int(buffer_size), BB_FALSE)
            iq = iq_struct["iq"]
            iq_buffer_start_nano = iq_struct["nano"]
            iq_buffer_start_sec = iq_struct["sec"]
            
            # Calculate the avg power using (iq * conj(iq) / total samples)
            avg_iq_power = np.abs(np.vdot(iq, iq) / buffer_size)
            
            # Check if it's over the threshold, if yes, add to event_list
            if (avg_iq_power >= mW_threshold) : 
                # calculate the dBm value
                avg_iq_power = 10 * np.log10(avg_iq_power)
                capture_time = datetime.fromtimestamp(iq_buffer_start_sec).strftime('%Y-%m-%d %H:%M:%S')
                event_list.append((capture_time, iq_buffer_start_nano, center_freq, avg_iq_power))
            i = i+1
            
elif args.option == 'sweep' :
    sweep_counter = 0
    time_list = []
    while (time.perf_counter() - measure_start_time) < duration :
        # Hop to next frequency channel with the same bandwidth and configure BB60C
        sweep_counter = (sweep_counter+1)%channel_number
        next_f = center_freq + sweep_counter*filter_bandwidth
        # print('Switch to capture at frequency : {}'.format(next_f)) #debug use
        test_reconf_start = time.perf_counter()
        bb_configure_IQ_center(handle, next_f)
        bb_initiate(handle, BB_STREAMING, BB_STREAM_IQ)
        time_list.append(time.perf_counter() - test_reconf_start)
        
        # Flush IQ data filter ramp up time
        garbage = bb_get_IQ_unpacked(handle, garbage_size, BB_TRUE)["iq"]
        i = 0
        while (i<num_captures_samefreq):
            # Here the parameter should be set BB_FALSE
            iq_struct = bb_get_IQ_unpacked(handle, int(buffer_size), BB_FALSE)
            iq = iq_struct["iq"]
            iq_buffer_start_nano = iq_struct["nano"]
            iq_buffer_start_sec = iq_struct["sec"]
            
            # Calculate the avg power using (iq * conj(iq) / total samples)
            avg_iq_power = np.abs(np.vdot(iq, iq) / buffer_size)
            
            # Check if it's over the threshold, if yes, add to event_list
            if (avg_iq_power >= mW_threshold) : 
                # calculate the dBm value
                avg_iq_power = 10 * np.log10(avg_iq_power)
                capture_time = datetime.fromtimestamp(iq_buffer_start_sec).strftime('%Y-%m-%d %H:%M:%S')
                event_list.append((capture_time, iq_buffer_start_nano, next_f, avg_iq_power))
            i = i+1
    
elif args.option == 'rand-sweep' : 
    while (time.perf_counter() - measure_start_time) < duration :
        # Randomly choose the next center frequency and configure BB60C
        next_f = center_freq + random.randrange(channel_number)*filter_bandwidth
        # print('Switch to capture at frequency : {}'.format(next_f)) #debug use
        bb_configure_IQ_center(handle, next_f)
        bb_initiate(handle, BB_STREAMING, BB_STREAM_IQ)
        
        # Flush IQ data filter ramp up time
        garbage = bb_get_IQ_unpacked(handle, garbage_size, BB_TRUE)["iq"]
        i = 0
        while (i<num_captures_samefreq):
            # Here the parameter should be set BB_FALSE
            iq_struct = bb_get_IQ_unpacked(handle, int(buffer_size), BB_FALSE)
            iq = iq_struct["iq"]
            iq_buffer_start_nano = iq_struct["nano"]
            iq_buffer_start_sec = iq_struct["sec"]
            
            # Calculate the avg power using (iq * conj(iq) / total samples)
            avg_iq_power = np.abs(np.vdot(iq, iq) / buffer_size)
            
            # Check if it's over the threshold, if yes, add to event_list
            if (avg_iq_power >= mW_threshold) : 
                # calculate the dBm value
                avg_iq_power = 10 * np.log10(avg_iq_power)
                capture_time = datetime.fromtimestamp(iq_buffer_start_sec).strftime('%Y-%m-%d %H:%M:%S')
                event_list.append((capture_time, iq_buffer_start_nano, next_f, avg_iq_power))
            i = i+1

elif args.option == 'hop-ifnot-busy' : 
    busy_count = num_captures_samefreq*occupancy_threshold
    next_f = center_freq
    while (time.perf_counter() - measure_start_time) < duration :
        # Stay capturing in same freq if occupancy rate is over the threshold
        if (busy_count/num_captures_samefreq) >= occupancy_threshold : 
            # Channel busy
            pass            
        else :
            # Channel not busy, hop
            next_f = center_freq + random.randrange(channel_number)*filter_bandwidth
            bb_configure_IQ_center(handle, next_f)
            bb_initiate(handle, BB_STREAMING, BB_STREAM_IQ)
            # Flush IQ data filter ramp up time
            garbage = bb_get_IQ_unpacked(handle, garbage_size, BB_TRUE)["iq"]
                
        i = 0
        busy_count = 0
        while (i<num_captures_samefreq):
            # Here the parameter should be set BB_FALSE
            iq_struct = bb_get_IQ_unpacked(handle, int(buffer_size), BB_FALSE)
            iq = iq_struct["iq"]
            iq_buffer_start_nano = iq_struct["nano"]
            iq_buffer_start_sec = iq_struct["sec"]
            
            # Calculate the avg power using (iq * conj(iq) / total samples)
            avg_iq_power = np.abs(np.vdot(iq, iq) / buffer_size)
            
            # Check if it's over the threshold, if yes, add to event_list
            if (avg_iq_power >= mW_threshold) : 
                # calculate the dBm value
                avg_iq_power = 10 * np.log10(avg_iq_power)
                capture_time = datetime.fromtimestamp(iq_buffer_start_sec).strftime('%Y-%m-%d %H:%M:%S')
                event_list.append((capture_time, iq_buffer_start_nano, next_f, avg_iq_power))
                busy_count = busy_count + 1
            i = i+1

elif args.option == 'hop-with-p' : 
    busy_count = num_captures_samefreq*occupancy_threshold
    next_f = center_freq
    while (time.perf_counter() - measure_start_time) < duration :
        # Stay capturing in same freq if occupancy rate is over the threshold
        if (busy_count/num_captures_samefreq) >= occupancy_threshold : 
            # Channel busy, stay in same freq with probability p_samefreq
            if random.uniform(0, 1) <= p_samefreq:
                pass
            else :
                next_f = center_freq + random.randrange(channel_number)*filter_bandwidth
                bb_configure_IQ_center(handle, next_f)
                bb_initiate(handle, BB_STREAMING, BB_STREAM_IQ)
                # Flush IQ data filter ramp up time
                garbage = bb_get_IQ_unpacked(handle, garbage_size, BB_TRUE)["iq"]
        else :
            # Channel not busy, hop
            next_f = center_freq + random.randrange(channel_number)*filter_bandwidth
            bb_configure_IQ_center(handle, next_f)
            bb_initiate(handle, BB_STREAMING, BB_STREAM_IQ)
            # Flush IQ data filter ramp up time
            garbage = bb_get_IQ_unpacked(handle, garbage_size, BB_TRUE)["iq"]
                
        i = 0
        busy_count = 0
        while (i<num_captures_samefreq):
            # Here the parameter should be set BB_FALSE
            iq_struct = bb_get_IQ_unpacked(handle, int(buffer_size), BB_FALSE)
            iq = iq_struct["iq"]
            iq_buffer_start_nano = iq_struct["nano"]
            iq_buffer_start_sec = iq_struct["sec"]
            
            # Calculate the avg power using (iq * conj(iq) / total samples)
            avg_iq_power = np.abs(np.vdot(iq, iq) / buffer_size)
            
            # Check if it's over the threshold, if yes, add to event_list
            if (avg_iq_power >= mW_threshold) : 
                # calculate the dBm value
                avg_iq_power = 10 * np.log10(avg_iq_power)
                capture_time = datetime.fromtimestamp(iq_buffer_start_sec).strftime('%Y-%m-%d %H:%M:%S')
                event_list.append((capture_time, iq_buffer_start_nano, next_f, avg_iq_power))
                busy_count = busy_count + 1
            i = i+1
            
else :
    print("Warning : unrecognized sweep option !!!")




print("Capturing done")
#%% Close device and write to csv file


# Close the BB60C device
print("Device closing ...")
bb_close_device(handle)


# Write event to csv file
print("Write capture event to the output csv <{}> file".format(output_filename))
output_path = os. getcwd() + '\\'

# For Windows
with open(output_path + output_filename + '.csv','w', newline='') as out:
# for linux : with open(output_path + output_file,'w') as out:
    csv_output = csv.writer(out)
    csv_output.writerow(['Event start time','Time in Nano second', 'Center Freq (Hz)', 'Avg Power (dBm)'])
    csv_output.writerows(event_list)
    #for row in data:
    #    csv_out.writerow(row)    

# Write Metadata file
# For Windows
with open(output_path + "Metadata-" + output_filename + '.csv','w', newline='') as out:
# for linux : with open(output_path + output_file,'w') as out:
    csv_output = csv.writer(out)
    csv_output.writerow(['Sampling Rate (M/s)', fs/1e6])
    csv_output.writerow(['Sweep option', args.option])
    csv_output.writerow(['Min Center frequency (MHz)', center_freq/1e6])
    csv_output.writerow(['Max Center frequency (MHz)', center_freq/1e6 + (channel_number-1)*filter_bandwidth/1e6])
    csv_output.writerow(['Filter Bandwidth (MHz)', filter_bandwidth/1e6])
    csv_output.writerow(['Total channels sweeping during capturing', channel_number])
#    csv_output.writerow(['Center frequency (Hz)', center_freq])
    csv_output.writerow(['Threshold (dBm)', args.threshold])
    csv_output.writerow(['Reference level (dBm)', ref_level])
    csv_output.writerow(['Total collection duration (min)', args.duration])
    csv_output.writerow(['Buffer duration/min event size (us))', args.bufferduration])
    csv_output.writerow(['Frequency dwell time (ms)', args.fcduration])
    csv_output.writerow(['Comments', args.comment[0]])
       





# #%%  Test iq acuiring power with different sample rate

# # Open device
# handle = bb_open_device()["handle"]

# test_decimation = 4
# total_collection_time = 5
# rounds = 5/0.5
# test_buffer_size = (40e6*0.5)/test_decimation
# filter_bandwidth = 8e6

# center_freq = 2410.0e6

# # Bandwidth limitation table (Decimation rate, sampling rate, Max BW): 
# #     (1, 40 Ms/s, 27 MHz)
# #     (2, 20 Ms/s, 17.8 MHz)
# #     (4, 10 Ms/s, 8 MHz)
# #     (8, 5 Ms/s, 3.75 MHz)
# #     (16, 2.5 Ms/s, 2 MHz)


# #### Start the first round of measurement
# accumulate_iq_power = 0.0

# # Configure device (first time)
# bb_configure_ref_level(handle, ref_level)
# bb_configure_gain_atten(handle, BB_AUTO_GAIN, BB_AUTO_ATTEN)
# bb_configure_IQ_center(handle, center_freq)
# bb_configure_IQ(handle, test_decimation, filter_bandwidth)

# # Initialize
# bb_initiate(handle, BB_STREAMING, BB_STREAM_IQ)

# # Flush IQ data filter ramp up time
# garbage = bb_get_IQ_unpacked(handle, garbage_size, BB_TRUE)["iq"]

# # capture <num_captures_samefreq> round in this center frequency
# i = 0
# while (i<rounds):
#     # Here the parameter should be set BB_FALSE
#     test_iq = bb_get_IQ_unpacked(handle, int(test_buffer_size), BB_FALSE)["iq"]
#     # Calculate the avg power using (iq * conj(iq) / total samples)
#     test_iq_power = np.abs(np.vdot(test_iq, test_iq) / test_buffer_size)
#     accumulate_iq_power = accumulate_iq_power + test_iq_power
#     i = i+1

# avg_iq_power = 10 * np.log10(accumulate_iq_power/rounds)
# print("avg_iq_power for {} sample rate is {} dBm".format(40/test_decimation, avg_iq_power))

# bb_close_device(handle)


    # # Write to default_conf.json file https://stackoverflow.com/questions/65674436/how-do-i-change-a-value-of-a-json-object-with-python
    # with open('default_conf.json') as conf_file:
    #     conf_var = json.load(conf_file)
    #     #print('acquire_threshold : {}'.format(conf_var["acquire_threshold"]))
    #     conf_var["acquire_threshold"] = avg_iq_power
    #     #print('acquire_threshold : {}'.format(conf_var["acquire_threshold"]))
    
    # format_json = json.dumps(conf_var, indent=4)
    # # Writing to default_conf.json
    # with open('default_conf.json', 'w') as outfile:
    #     outfile.write(format_json)
    # sys.exit("Finish acquiring iq power")

