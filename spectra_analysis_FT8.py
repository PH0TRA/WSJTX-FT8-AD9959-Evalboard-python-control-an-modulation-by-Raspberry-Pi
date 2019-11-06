# -*- coding: utf-8 -*-
"""
Created on Mon Oct  7 20:43:54 2019

@author: marcburgmeijer
"""

"""
if you don't have pyaudio, then run
>>> pip install pyaudio
info used while programming MBu
https://stackoverflow.com/questions/35970282/what-are-chunks-samples-and-frames-when-using-pyaudio
    
Adapted for transferring the audio tone of WSJTX to an DDS syntheziser
in order to directly generate a FT8 FSK signal. 
FT8 generates 79 bits in 12.6 seconds, so the frame rate must be 6.250 frames/second to
capture every tone. The tone spacing is 6.25 Hz.

"""


import numpy as np
import pyaudio
import queue
import struct
from scipy.fftpack import fft
import time
import sys



##script to supress all the alsa errors https://stackoverflow.com/questions/7088672/pyaudio-working-but-spits-out-error-messages-each-time
from ctypes import *
from contextlib import contextmanager

ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)

def py_error_handler(filename, line, function, err, fmt):
    pass

c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)

@contextmanager
def noalsaerr():
    asound = cdll.LoadLibrary('libasound.so')
    asound.snd_lib_error_set_handler(c_error_handler)
    yield
    asound.snd_lib_error_set_handler(None)

# %%

class AudioStream(object):
    def __init__(self, Workqueue):
        self.qdata=Workqueue
        self.pause = False
          
        # stream constants
        self.CHUNK = int(7056)#gives 6,25 Hz spacing
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = int(44100)#native samplerate otherwise pyaudio won't work
        self.min_freq=400
        self.min_sample=self.min_freq*self.CHUNK//self.RATE ##set underlimit of frequency
        
        # stream object
        with noalsaerr():
            self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            output=True,
            frames_per_buffer=self.CHUNK,
        )    
        self.calculate_plot()


    def calculate_plot(self):

        print('stream started')
        frame_count = 0
        start_time = time.time()
        fr=0
               
        
        while not self.pause:
            data = self.stream.read(self.CHUNK) ##stream of binary data
            data_int = struct.unpack(str(2 * self.CHUNK) + 'B', data)
            
            # compute FFT and update line
            yf = fft(data_int) ##compute FFT
            ydata=np.abs((yf[0:self.CHUNK]) / (128 * self.CHUNK))##normalized levels to max 1 value and absolute out of complex
            
            ydata_amax=np.max(ydata[self.min_sample:self.CHUNK//2])##return maximum value maximum half samplerate otherwise aliasing occurs
            ydata_argmax=np.argmax(ydata[self.min_sample:self.CHUNK//2])+self.min_sample## return position  of maximum value (check but remember 1st is skipped)
            
            fr = frame_count / (time.time() - start_time)
            
            d_freq=(ydata_argmax)*self.RATE/(self.CHUNK)
            
            if ydata_amax <= 0.2 or d_freq >=2400 : ##test maximum value and return frequency
                d_freq=0
            
                            
            try:
                self.qdata.put_nowait(d_freq)#,timeout=1)#(dict(f=d_freq))
            except queue.Full:
                self.pause=True
                
                
            sys.stdout.flush()
            frame_count += 1
##            t=start_time + frame_count*12.6/79 - time.time()
##            if t < 0: t = 0
##            time.sleep(t)## just in case if framerate is shorter than FT8 tone
        
        else:
            fr = frame_count / (time.time() - start_time)
            print('average frame rate = {0:.3f} FPS'.format(fr))
            print('number of lines:', len(ydata))
            print('linewidth = {0:.3f} Hz'.format(self.RATE/len(ydata)))
            self.exit_app()
    

    def exit_app(self):
        print('stream closed')
        self.p.close(self.stream)
        

    def onClick(self, event):
        self.pause = True
        
    

