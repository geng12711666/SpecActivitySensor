# SpecActivitySensor using BB60C

This python script contains code that can capture channel activity by measuring and monitoring the iq power in different frequency bands using BB60C spectral analyzer. Users may configure BB60C as well as other measuring parameters with either command line argument or configuration .json file. The script will then start sweeping on interested band based on different sweeping option to perform the IQ acquisition, processing, and thresholding. All spectrum activities will be recorded as events and write to the output file.

**Input** :
 
	- configuration json file(optional)
	
**Output** : 

    - <output_filename>.csv : Event list that captures the events in the specified channels. Each event contains the event start time(down to nano second percision), center freqency of the capturing event, and the average power in dBm. The event bandwidth and duration can be found in <Filter Bandwidth (MHz)> & <Buffer duration/min event size (us))> in Metadata file, respectively.
    - Metadata-<output_filename>.csv : Metadata of the Capturing. 
    - (Optional) <config_name>.json : The configuration of this capturing. This will be output only if -w/--writeconfig is called


**DISCLAIMER**: Certain tools, commercial equipment, instruments, or materials are identified in this repository in order to specify the experimental procedure adequately.  Such identification is not intended to imply recommendation or endorsement by NIST, nor is it intended to imply that the materials or equipment identified are necessarily the best available for the purpose.


## Requirements and Prerequisite
**Hardware**
* BB60C : 6 GHz Real-time Spectrum Analyzer from SignalHound
* PC : PC that can support the BB60C. See BB60C document for more details. The script has been tested and verified on win 10.

**Software**
* Signal Hound Software Development Kit (SDK) : Include the device-specific API(windows DLL, C interface) to communicate with BB60C. The kit can be downloaded here : https://signalhound.com/software/signal-hound-software-development-kit-sdk/ 
* Python 3 : The script has been tested and verified with python 3.10.
* argparse, SciPy, NumPy and other used python packages

**Pre-steps**
* Signal Hound SDK (windows): 
	- Place the bb_api.py and bb_api.dll files into the bbdevice/ folder.
	- Add the bbdevice folder to the Python search path and to the system path. (More details for the first two steps can be seen in the README file in Signal Hound SDK)
	- Modify the variable value **API_directory** with your own folder path.
	 

## How it Works
![Illustration for activity capturing by sensor](figures/Activity-Capture.png)
Illustrate in the figure above, the snesor will sweep through the designated frequency span, dwelling on one frequency channel with specific filter bandwidth for a certain of time(**dwell time**), and measuring the channel iq power. The sensor will collect the average channel power for the periaod of time(**buffer time**) repeatly, and write to the output event file if the average power is above the designated threshold. Once done capturing in one channel over dwell time, the sensor will hop to another frequency with the same channel bandwidth for another round of capturing. The whole capturing process will continue for the **collection duration**. See the following figure for the process flow :
![Process flow](figures/process-flow.png)

## Sweep Options
The script provides several sweep options for patterns of hopping during sweep :
* fixed : 			No hopping, capturing in the same frequncy.
* sweep : 			Sweep through channels through the whole span in order.
* rand-sweep : 		Randomly hop through channels with equally distributed probablity.
* hop-ifnot-busy :	Randomly hop to another channel only if the channel is not busy (occupancy rate less than *occupancy_threshold*)
* hop-with-p : 		Stay in current frequency with the probability *p_samefreq* for busy channel, otherwise randomly hop to other channel.

*occupancy_threshold* & *p_samefreq* are currently set to 30% and 0.7, respectively.

## Acquire Option and Configuration File
The script provide the *acquire* option to measure the environment average channel power for the specifuc amount of time. This is useful for getting the noise floor for thresholding. Normally the environmental noise floor plus an offset will be used for the sensor threshold. The offset is default to 10dBm.

The configuration file allows users to remember the settings of a specific measurement and reuse the same settings in the future. The configuration file is in the form of .json file.



# Table of Max Filter Bandwidth for Different Sampling Rate
In BB60C, there's a limitation for max filter bandwidth used under different sampling rate. User should not specify the filter bandwidth greater than this limit. See the table below : 
![Max filter bandwidth table](figures/bandwidth-table.png)
Notice that the max filter bandwidth will be used if not specified.

# Examples
1. Perform capturing that sweeps from 2410 Mhz to 2510 Mhz with default settings (5 Ms/s sampling rate, 3.75 MHz filter bandwidth, 50us buffer time and 10ms dwell time) for an hour. Output the result with filename *example1* : 
	- *channel-capturing -o example1 -f 2410 -s 100 --comment "This is Example 1"*

2. Acquire for noise floor for 10 seconds, and also write the settings "span from 3500 Mhz to 3800 Mhz with *rand-sweep* sweep option" to configuration file *example2.json*. And then use the produced configuration file to do the capturing and output to file *example2* :
	- *channel-capturing --acquire 10 -f 3500 -s 300 --option rand-sweep -w example2*
	- *channel-capturing --conf example2 -o example2 --comment "This is Example2 with imported configuration file and acquire option"*

# Usage
*channel-capturing [-h] [-o <output_filename>]
                       [--conf <configuration_file>] [-f <center_freq>]
                       [-s <Sweep_span>] [-fb <filter_bandwidth>]
                       [-ref <reference_level>] [-th <Threshold>]
                       [-d <Fs_decimation>] [-t <Collection_duration>]
                       [-b <Buffer_duration>] [-ft <Fc_dwelltime>]
                       [--acquire <acquire_time> ]
                       [-w <config_filename>]
                       [--offset <threshold_offset>]
                       [--option <Sweep_option>]
                       [--comment "<your comments>"]*

**options:**

  -h, --help            show this help message and exit
  
  -o <output_filename>, --output <output_filename>
                        Set the output file name. Default name will be py-
                        out-\<current time>
						
  --conf <configuration_file>
                        Configuration file for the argparse
						
  -f <center_freq>, --frequency <center_freq>
                        Start Center frequency (MHz) of the sweep measurement.
                        Frequency should be in the range of sub-6 Ghz. Default
                        to 2410.0 MHz
						
  -s <Sweep_span>, --span <Sweep_span>
                        Total Sweep span (MHz) of the measurement. The real
                        sweeping span may be different based on the
                        filter_bandwidth. Default mode is no sweeping
						
  -fb <filter_bandwidth>, --filter_bandwidth <filter_bandwidth>
                        Bandwidth (MHz) of the iq capturing on specific center
                        frequency. For BB60C different max bandwidth for
                        different sample rate is specified in the bandwidth
                        limitation table
						
  -ref <reference_level>, --reference <reference_level>
                        Reference level (dBm) for the device. Default to
                        -20dBm and should not set too low to prevent damaging
                        the device
						
  -th <Threshold>, --threshold <Threshold>
                        Threshold value (dBm) for the post processing. Only
                        output the event having power larger than the
                        threshold. Default to -45dBm.
						
  -d <Fs_decimation>, --decimation <Fs_decimation>
                        Decimation value for sampling frequency(can only be
                        power of 2). The Sample frequency = 40/(decimation)
                        Ms. Default to 8.
						
  -t <Collection_duration>, --duration <Collection_duration>
                        Collection duration (min). Default to 1 min.
						
  -b <Buffer_duration>, --bufferduration <Buffer_duration>
                        The collection time to buffer for each measurement
                        acquisition (us). Default to 50us.
						
  -ft <Fc_dwelltime>, --fcduration <Fc_dwelltime>
                        The dwell time for the capturing staying in one
                        frequency (ms). Default to 10ms.
						
  --acquire <acquire_time>
                        The acquire time for the threshold for the noise floor
                        (sec). Default to 5s. If --acquire option is called,
                        it will capture and average the IQ data in
                        <acquire_time> and then set the acquire_threshold in
                        default_conf.json file
						
  -w <config_filename>, --writeconfig <config_filename>
                        Output the current configuration to a configuration
                        json file with name <config_filename>. Default name
                        will be config-\<current time>
						
  --offset <threshold_offset>
                        The offset added on the acquired noise floor (dBm).
                        This is only effective if the --acquire option is
                        called. The threshold value written to the
                        configuration file will be (acquired_noise_floor +
                        threshold_offset). Default to 10dBm.
						
  --option <Sweep_option>
						Sweep options for frequency hopping. Default to sweep
  
  --comment "<your comments>"
                        This option helps writing comments with content "<your
                        comments>" to output Metadata file. Remember to add
                        the double quote ("") to your comments.



# Contact Information
Jing Geng, NIST <br>
Email : jing.geng@nist.gov
