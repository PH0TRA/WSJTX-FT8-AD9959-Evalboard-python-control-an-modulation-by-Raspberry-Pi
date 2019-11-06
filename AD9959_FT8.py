#!/usr/bin/python3

##libraries
import RPi.GPIO as GPIO
import spectra_analysis_FT8 as FT8
import time, sys, spidev, argparse, re, threading, queue

FT8_freq={  '160m' : '1840000',
            '80m' : '3573000',
            '40m' : '7074000',
            '30m' : '10136000',
            '20m' : '14074000',
            '17m' : '18100000',
            '15m' : '21074000',
            '12m' : '24915000',
            '10m' : '28074000',
            '6m' : '50313000',
            '2m' : '144174000'
           }
frequencies=[]
qdata=queue.Queue(maxsize=7)

## set variables
spi=spidev.SpiDev()
spi.open(0,0)
spi.max_speed_hz= 200000
#spi.no_cs=True


UPD=23 # GPIO 23 to I/O_update on AD9959
RESET=24 # GPIO 24 RESET
## GPIO 10 (SPI_MOSI) to SDIO 0 on AD9959
## GPIO 9 (SPI_MISO) to SDIO 2
## GPIO 11 (SPI_CLOCK) to SCLK
## GPIO 8 (SPI_CE0_N) to CSB


##setup GPIO
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(UPD,GPIO.OUT)
GPIO.setup(RESET,GPIO.OUT)


#%%
##setup default values for registers
multp=20
offset=0 # in Hz from reference clock

IBR=0b10000000#instruction byte read
IBW=0b00000000#instruction byte wrtite
#CSR=0b11110010#0xF0 all channels, msb mode, 3 wire mode
FR1a=0b11010000#bit[23:16]
FR1b=0b00000000#'#bit[15:8]
FR1c=0b00000000#bit[7:0]
FR2a=0b00000000#bit[15:8]
FR2b=0b00000000#bit[7:0]
CFRa=0b00000000#bit[23:16]
CFRb=0b00000011#bit[15:8]
CFRc=0b00000010#bit[7:0]
#ACRa=0b00000000#bit[23:16]
#ACRb=0b00010011#bit[15:8]
#ACRc=0b10000000#bit[7:0]
LSRRa=0b00000000#bit[15:8]
LSRRb=0b00000000#bit[7:0]
RDWa=0b00000000#bit[31:24]
RDWb=0b00000000#bit[23:16]
RDWc=0b00000000#bit[15:8]
RDWd=0b00000000#bit[7:0]
FDWa=0b00000000#bit[31:24]
FDWb=0b00000000#bit[23:16]
FDWc=0b00000000#bit[15:8]
FDWd=0b00000000#bit[7:0]


#%% Functions

def UPDATE():
    GPIO.output(UPD,1) ##syncIO
    GPIO.output(UPD,0)

def AD9959(reg,word):  
    regmap={
        'CSR':(0x00,1),'FR1':(0x01,3),'FR2':(0x02,2),'CFR':(0x03,3),'CFTW':(0x04,4),'CPOW':(0x05,2),
        'ACR':(0x06,2),'LSRR':(0x07,2),'RDW':(0x08,4),'FDW':(0x09,4)
        } 
    transfer=[regmap[reg][0]]+word
    #for i in transfer:
    #    print('{0:08b}'.format(i))
    spi.xfer(transfer)
    return()

def READ(reg):
    regmap={
        'CSR':(0x00,1),'FR1':(0x01,3),'FR2':(0x02,2),'CFR':(0x03,3),'CFTW':(0x04,4),'CPOW':(0x05,2),
        'ACR':(0x06,2),'LSRR':(0x07,2),'RDW':(0x08,4),'FDW':(0x09,4)
        }
    transfer=regmap[reg][0]+0x80
    #print('{0:08b}'.format(transfer))#generate instructionbyte
    spi.xfer([transfer])
    ln=regmap[reg][1]
    byte=spi.readbytes(ln)
    return(byte)

def CSR(ch):
    csr = ((0b00010000 << ch) + 0b00000010) #shift channel bit
    return([csr])

def CFTW(freq,multp):
        FTW=int((freq*2**32)/((25e06+offset)*multp))
        f4 = int(FTW & 0xff) #split into four bytes: mask last 8 bits and shift
        f3 = int((FTW >> 8) & 0xff) 
        f2 = int((FTW >> 16) & 0xff)
        f1 = int(FTW >> 24)
        return([f1,f2,f3,f4])

def ACR(power):
        ACRc = int(power & 0xff)#bit[7:0]
        ACRb = int(((power >> 8) & 0xff) + 0b00010000)#bit[15:8]
        ACRa=0b00000000#bit[23:16]
        return([ACRa,ACRb,ACRc])

#%% Argument parser

usage='Script to control Analog Devices AD9959'
usage_freq='F0 to F3 frequency in Hz or standard FT8 frequency e.g. "14097100" or "10m". "K"(Hz) or "M"(Hz) may be used.' 
usage_pow='power for each channel value 0-1023 default 1023'
p=argparse.ArgumentParser(description=usage)

p.add_argument('-f','--FT8', action='store_true', dest='FT8',
             help='Transmit on base frequency shifted with tone input of WSJTX'
             )
p.add_argument('frequencies', metavar='F', nargs=4, help=usage_freq)

p.add_argument('power0', metavar='P0', nargs='?', help=usage_pow, default='1023', type=int)
p.add_argument('power1', metavar='P1', nargs='?', help=usage_pow, default='1023', type=int)
p.add_argument('power2', metavar='P2', nargs='?', help=usage_pow, default='1023', type=int)
p.add_argument('power3', metavar='P3', nargs='?', help=usage_pow, default='1023', type=int)

output = p.parse_args()
#print(output)


for frequency in output.frequencies:#get the frequencies from the list
    #print(frequency)
    try:
        f=int(FT8_freq[frequency]) #get known WSPR frequency
        frequencies.append(f)
    except:
        try:
            if re.search('[K]$',frequency):
                frequency=frequency.replace('K','000')
            if re.search('[M]$',frequency):
                frequency=frequency.replace('M','000000')      
            f=int(frequency) #else it must be an integer value
            frequencies.append(f)
        except:
            print('Malformed frequency.',file=sys.stderr) 
            print(usage_freq, file=sys.stderr)
            sys.exit(-1)

print("Channel 0 set to: {0:,} Hz: power set to: {1:d}".format(frequencies[0],output.power0))
print("Channel 1 set to: {0:,} Hz: power set to: {1:d}".format(frequencies[1],output.power1))
print("Channel 2 set to: {0:,} Hz: power set to: {1:d}".format(frequencies[2],output.power2))
print("Channel 3 set to: {0:,} Hz: power set to: {1:d}".format(frequencies[3],output.power3))

power=[output.power0, output.power1, output.power2, output.power3]

if __name__ == '__main__':

    #%% Reset and setup 
    GPIO.output(RESET,1)
    time.sleep(0.01)
    GPIO.output(RESET,0)

    #write FR1
    AD9959('FR1',[FR1a,FR1b,FR1c])

    #%% write each channel

    for i in range(0,4):
        ##write CSR
        AD9959('CSR',CSR(i))

        ##write frequency
        AD9959('CFTW',CFTW(frequencies[i],multp))
        
        # write ACR
        AD9959('ACR',ACR(power[i]))

    UPDATE()

    #%%
##    status=READ('CFTW') #read current status of CSR byte
##    for r in status:
##        print(r)
##        print('({0:08b})'.format(r))
        
    #%%
    if output.FT8:
        AD9959('CSR',CSR(0)) ##FT8 to channel 0!
        AD9959('CFTW',CFTW(0,multp))
        UPDATE()
        t = threading.Thread(target=FT8.AudioStream, args = (qdata, ))
        t.start() ##starts the class Audiostream
        print('thread running')
        #time.sleep(2)
        frame_count = 0
        start_time = time.time()

        try:
            while True:#not qdata.empty():
                #pass
                d=qdata.get(timeout=2)
                if d != 0:
                    FT8_freq=frequencies[0]+d
                else:
                    FT8_freq=0
                AD9959('CFTW',CFTW(FT8_freq,multp))
                UPDATE()
                print(d, end=',')
                frame_count += 1
                
        except queue.Empty:#(queue.Empty,KeyboardInterrupt) as exc: 
            fr = frame_count / (time.time() - start_time-2)
            t.join()
            print()
            print('average frame rate = {0:.3f} FPS'.format(fr))
            print('program finished')
            
        except KeyboardInterrupt: 
            fr = frame_count / (time.time() - start_time)
            t.join()
            print()
            print('average frame rate = {0:.3f} FPS'.format(fr))
            print('program finished')
