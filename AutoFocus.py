import tkinter
import cv2
import PIL.Image, PIL.ImageTk
import time
from imutils import paths
import serial
import numpy as np
from configparser import ConfigParser
import os.path

#Set this to true if you need the debug prints
debug = False

multiplier = 10 #default value
# If the configuration file is found, load the Settings from that
if os.path.isfile('settings.ini'):
    configur = ConfigParser() 
    configur.read('settings.ini') 
    
    multiplier = int(configur.get('autofocus','scanRangeMultiplier'))
    print ("Settings Loaded from file. Scan Range Multiplier = {}".format( multiplier)) 
else:
    print("'settings.ini' not found. Using the default values")
    
scan1_range = 512*multiplier     
scan1_steps = multiplier
#scan1_range =5120     #This is the range which the camera will move in the 1st scan (in steps. 800steps/5mm)
#scan1_steps = 10       #The number of stops of the camera moving in the scan1 range
scan2_range = scan1_range/scan1_steps      #Range of the 2nd scan (This is done for fine tuning. So range should be 2*(scan1_range/scan1_steps) usually.
scan2_steps = 2       #Number of stops in the 2nd scan
scan3_range = scan2_range/scan2_steps
scan3_steps = 4
scan4_range = scan3_range/scan3_steps
scan4_steps = 4
scan5_range = scan4_range/scan4_steps
scan5_steps = 4
scan6_range = scan4_range/scan4_steps
scan6_steps = 4




#scan_range_list = [scan1_range, scan2_range, scan3_range, scan4_range, scan5_range, scan6_range]
#scan_steps_list = [scan1_steps, scan2_steps, scan3_steps, scan4_steps, scan5_steps, scan6_steps]

scan_range_list = [scan1_range,512,256,128,64,32,16,8,4,2]
scan_steps_list = [scan1_steps,2,2,2,2,2,2,2,2,2]
scan_k = [10,0,0,0,0,0,0,0,0,0]
scan_k2 = [1,2,2,2,2,2,2,2,2,2]

class App:
    #This is the initialization of the GUI window and the global variables used in the application
    def __init__(self, comport, video_source=0):

        self.window = tkinter.Tk()
        self.window.title("AutoFocus v0.1")
        self.video_source = video_source

        
        self.initVariables()
        self.openArduino(comport)   #Opens arduino for communication

        # open video source (by default this will try to open the computer webcam)
        self.vid = MyVideoCapture(self.video_source)
        self.start = False  # 'Focus' button

        # Create a canvas that can fit the above video source size
        self.canvas = tkinter.Canvas(self.window, width = self.vid.width, height = self.vid.height)
        #self.canvas = tkinter.Canvas(window, width = w, height = h)
        self.canvas.pack()

        #Manual control buttons
        self.buttonFrame = tkinter.Frame(self.window) 
        self.buttonFrame.pack(side = tkinter.RIGHT)
        self.forwardButton = tkinter.Button(self.buttonFrame, text = 'Camera Forward', fg ='white', bg = 'blue', width=20, command=self.manualForward) 
        self.forwardButton.pack(side = tkinter.TOP)
        self.backwardButton = tkinter.Button(self.buttonFrame, text = 'Camera Backward', fg ='white', bg = 'blue', width = 20, command=self.manualBackward) 
        self.backwardButton.pack(side = tkinter.BOTTOM)


        # Button that lets the user take a snapshot
        self.btn_snapshot=tkinter.Button(self.window, text="Focus", fg= 'black', bg = 'green', width=20, command=self.autofocus)
        self.btn_snapshot.pack(anchor=tkinter.CENTER, expand=True)
        self.btn_stop=tkinter.Button(self.window, text="Stop", fg= 'black', bg = 'red', width=20, command=self.stopFocus)
        self.btn_stop.pack(anchor=tkinter.CENTER, expand=True)

        self.labelContent = tkinter.StringVar()
        self.infoLabel = tkinter.Label(self.window, textvariable=self.labelContent)
        self.infoLabel.pack(anchor=tkinter.CENTER)
        self.labelContent.set("Click to start") # This can change the text under the button
 
        # After it is called once, the update method will be automatically called every delay milliseconds
        self.delay = 10  # delay between each frame
        self.update()

        self.window.mainloop()

    def autofocus(self):
        
        self.start = True
        #True
    
    def stopFocus(self):
        self.initVariables()
        self.start = False
        self.labelContent.set("Stopped. Click 'Focus' to start")
       

    def update(self):
        # Get a frame from the video source
        ret, frame = self.vid.get_frame()

        if ret:
            if not self.start:
                #Before starting the focus program, this will keep displaying the camera feed.
                self.photo = PIL.ImageTk.PhotoImage(image = PIL.Image.fromarray(frame))
                self.canvas.create_image(0, 0, image = self.photo, anchor = tkinter.NW)
                self.checkStartButton()

            else: #Autofocus procedure

                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                fs = cv2.Laplacian(frame, cv2.CV_64F).var() #Measure of the focus level of the image

                self.position_focus[int(self.current_position)] = 2*round(fs/2)
                #self.position_focus[int(self.current_position)] = max(fs,self.position_focus[int(self.current_position)])
                #Display the frame
                self.photo = PIL.ImageTk.PhotoImage(image=PIL.Image.fromarray(frame))
                self.canvas.create_image(0, 0, image=self.photo, anchor=tkinter.NW)
                self.max_focus = max(self.position_focus)
                self.labelContent.set("Focus score : {} \t Max : {}".format(self.position_focus[int(self.current_position)],self.max_focus))

                if not self.focusCompleted:
                    if debug:
                        print("Scan {} : range : {} / {}".format(self.scan_number,scan_range_list[self.scan_number],scan_steps_list[self.scan_number]))
                    self.scan()
                else:
                    if(self.checkStartButton()):
                        self.initVariables()
                #time.sleep(0.1)
                

                
                

        self.window.after(self.delay, self.update)

    def initVariables(self):
        #Variables
        self.max_focus = 0                                          # Stores the max focus value
        self.position_focus = [0] * 40000                           # This is an array saving the focus values for each position (lenght 40000)
        self.current_position = int(len(self.position_focus)/2)     # Stores the current position of the camera. Initialized to center : 20000
        self.init_position = self.current_position                  # Saves the starting postion for each scan
        self.move_command = ['first','forward',0]                   # This is the move command, updated in each step of the scans
        # The 3 elements in the move_command are, ['scan#','direction,'steps to move']
        self.inverted = False
        self.scan_number = 0
        self.scan_range = scan_range_list[self.scan_number]
        self.scan_steps = scan_steps_list[self.scan_number]
        self.focusCompleted = False

    def scan(self):

        if debug:
            print("Position : {} \t Focus Value : {} \t Max focus : {}".format(self.current_position,self.position_focus[int(self.current_position)],self.max_focus))
        skip = False




        #inverting logic
        if ((self.current_position == self.init_position + int(3*self.scan_range/self.scan_steps)) and \
            self.position_focus[int(self.current_position)] < self.position_focus[int(self.init_position)]\
            or ((self.current_position == self.init_position + int(8*self.scan_range/self.scan_steps))\
            and (max(self.position_focus) <= self.position_focus[self.init_position] + 2))):
            if debug:
                print("Current pos : {}\t comp pos : {}".format(self.current_position,self.init_position + int(2*self.scan_range/self.scan_steps)))
            self.scan_range = - self.scan_range
            self.writeToArduino(self.init_position - self.current_position)
            self.waitForArduino()
            self.current_position = self.init_position
            print("Inverting direction")
            skip = True

        #Stop if the screen is blank
        elif ((self.position_focus[int(self.current_position)] < 2) \
        and(self.position_focus[int(self.current_position - self.scan_range/self.scan_steps)] < 2)\
        and (self.position_focus[int(self.current_position - 2* self.scan_range/self.scan_steps)] < 2)\
        and (self.position_focus[int(self.current_position - 3* self.scan_range/self.scan_steps)] < 2)\
        ):
            self.stopFocus()
            self.labelContent.set("ERROR : No response from the camera")

        #Scan termination logic
        elif(self.position_focus[int(self.current_position)]+scan_k[self.scan_number] < self.position_focus[int( \
            self.current_position - (scan_k2[self.scan_number]*self.scan_range / self.scan_steps))] or self.current_position == self.init_position + self.scan_range):
            if debug:
                print("scan range : {} \t scan steps : {}".format(self.scan_range,self.scan_steps))
            if not int(abs(self.scan_range/self.scan_steps)) <= 1:
            
                self.scan_number = self.scan_number + 1
                if self.scan_range > 0:
                    self.scan_range = - scan_range_list[self.scan_number]
                else:
                    self.scan_range = scan_range_list[self.scan_number]
                
                self.scan_steps = scan_steps_list[self.scan_number]
                target_position = self.position_focus.index(max(self.position_focus)) - int(self.scan_range / 2)
                if debug:
                    print("Next scan")
            else:
                target_position = self.position_focus.index(max(self.position_focus))
                self.focusCompleted = True
                print("Focus completed")
                self.labelContent.set("Focus Completed!")
                time.sleep(5)

            self.writeToArduino(target_position - self.current_position)
            self.waitForArduino()
            self.init_position = target_position
            self.current_position = self.init_position
            if debug:
                print("Returning to position : {}".format(self.current_position))
            skip = True

        if (not self.focusCompleted) and (not skip):
            if debug:
                if self.scan_range > 0:
                    print("Moving forward : {}".format( self.scan_range/self.scan_steps))
                elif self.scan_range < 0:
                    print("Moving backward : {}".format(-self.scan_range/self.scan_steps))

            self.writeToArduino(self.scan_range / self.scan_steps)
            self.waitForArduino()
            self.current_position = self.current_position + self.scan_range / self.scan_steps

    #Opening com port for serial communication
    def openArduino(self,comport):
            self.s = serial.Serial(comport, baudrate=9600, timeout = 0, write_timeout = 0)
            print(self.s.name)
            time.sleep(0.5)

    #Close the com port at the end
    def closeArduino(self):
            self.s.close()

    #Write values to arduino
    def writeToArduino(self,num):
            self.s.write(str(num).encode('UTF-8'))

    #Wait for arduino acknowledge signal to confirm the complesion of the movement
    def waitForArduino(self):
            ard = 'x'
            while not ard == 'a':
                    ard = self.s.read_until("\n").decode('utf-8')
                    if ard == 'l':
                        self.stopFocus()
                        self.labelContent.set("ERROR : Slider hit a limit")
                        break

    def checkStartButton(self):
        ard = self.s.read_until("\n").decode('utf-8')
        if ard == 's':
            self.start = True
            return True

    def manualForward(self):
        self.writeToArduino(500)
        self.waitForArduino()

    def manualBackward(self):
        self.writeToArduino(-500)
        self.waitForArduino()

 

#Custom wrapper for capturing video feed.
class MyVideoCapture:
    def __init__(self, video_source=0):
        # Open the video source
        self.vid = cv2.VideoCapture(video_source)
        if not self.vid.isOpened():
            raise ValueError("Unable to open video source", video_source)

        # Get video source width and height
        self.width = self.vid.get(cv2.CAP_PROP_FRAME_WIDTH)
        self.height = self.vid.get(cv2.CAP_PROP_FRAME_HEIGHT)

    def get_frame(self):
        if self.vid.isOpened():
            ret, frame = self.vid.read()
            if ret:
                # Return a boolean success flag and the current frame converted to BGR
                return (ret, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            else:
                return (ret, None)
        else:
            return (ret, None)

    # Release the video source when the object is destroyed
    def __del__(self):
        if self.vid.isOpened():
            self.vid.release()

#Main object of the program
# Create a window and pass it to the Application object
#App(tkinter.Tk(), "AutoFocus v0.1",'COM95') #Set the COM PORT here
