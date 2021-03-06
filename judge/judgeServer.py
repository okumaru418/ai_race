# -*- coding: utf-8 -*-
import os
import datetime
import time
from enum import Enum
import argparse
import json
import threading
import pprint
## flask
from flask import Flask, request, jsonify, render_template
from flask import send_from_directory
## for server debug logger
import logging
from logging.handlers import RotatingFileHandler

## general definition
DEFAULT_GAME_TIME=240
DEFAULT_TIME_MODE=1

## flask
app = Flask(__name__)

## time mode
class TimeMode(Enum):
    SYSTEM_TIME = 1
    ROS_TIME = 2

class TimeManagementClass():
    def __init__(self):
        self.start_time = 0.00
        self.elapsed_time = 0.00
        self.current_time = 0.00

    def init_time(self):
        self.start_time = 0.00
        self.elapsed_time = 0.00
        self.current_time = 0.00

class GameManagerClass:

    ####
    # State
    #  Init --> Start --> Stop
    ####
    
    def __init__(self, args):
        self.time_max = args.gametime # [sec]
        self.time_mode = args.timemode
        self.system_time = TimeManagementClass() # system time
        self.ros_time = TimeManagementClass()    # ros time
        self.initGameData()

    def setJudgeState(self, state):
        app.logger.info("setState")
        if state != "init" and state != "start" and state != "stop":
            print("invalid state." + state)
            return False

        self.judgestate = state

        # [fixme] this data should be registered from prepare.sh
        # for level1 data
        # position x,y,z / orientation x,y,z,w
        self.CourseOutRecoveryLocationList = {
            "index": [
                [1.75, 0.50, 0.75, 0, 0, 0.3, 0.3]
            ]
        }

        return True

    def initGameData(self):
        self.setJudgeState("init")
        self.system_time.init_time()
        self.ros_time.init_time()
        self.lap_count = 0
        self.recovery_count = 0
        self.courseout_count = 0
        self.is_courseout = 0

    def startGame(self):
        self.setJudgeState("start")
        self.system_time.start_time = time.time()
        self.ros_time.start_time = self.ros_time.current_time
        return True

    def stopGame(self):
        if self.judgestate == "stop":
            return True
        self.setJudgeState("stop")
        self.writeResult()
        return True

    def requestToServer(self, body):
        app.logger.info("requestToServer")

        # check what is requested
        ## change_state
        if "change_state" in body:
            change_state = body["change_state"]
            if change_state == "init":
                self.initGameData()
            elif change_state == "start":
                self.startGame()
            elif change_state == "stop":
                self.stopGame()
            else:
                print("invalid request")
                return False
        else:
            print("invalid request")
            return False
        return True

    def is_timeover(self):
        if self.time_mode == TimeMode.SYSTEM_TIME:
            if self.system_time.elapsed_time < self.time_max:
                return False
        else: # ROS_TIME
            if self.ros_time.elapsed_time < self.time_max:
                return False
        return True

    def updateTime(self):
        #app.logger.info("updateTime")
        if self.system_time.start_time == 0:
            self.system_time.elapsed_time = 0.00
            return False

        # update time
        self.system_time.elapsed_time = time.time() - self.system_time.start_time
        self.ros_time.elapsed_time = self.ros_time.current_time - self.ros_time.start_time
        # check if time is over
        if self.is_timeover() == True:
            self.stopGame()

        #app.logger.info("elapsed_time {}".format(self.elapsed_time))
        return True

    def updateData(self, body):
        app.logger.info("updateData")

        # check which data is requested to update
        ## lap count
        if "lap_count" in body:
            self.lap_count = self.lap_count + int(body["lap_count"])
        if "courseout_count" in body:
            self.courseout_count = self.courseout_count + int(body["courseout_count"])
        if "recovery_count" in body:
            self.recovery_count = self.recovery_count + int(body["recovery_count"])
        if "is_courseout" in body:
            self.is_courseout = int(body["is_courseout"])
            print(self.is_courseout)
        if "current_ros_time" in body:
            self.ros_time.current_time = float(body["current_ros_time"])
        return True

    def getGameStateJson(self):
        self.updateTime()

        # state data to json
        json = {
            "field_info": {
                "description": "field information",
                "CourseOutRecoveryLocationList": self.CourseOutRecoveryLocationList,
            },
            "vehicle_info": {
                "description": "vehicle information",
            },
            "judge_info": {
                "description": "judge information",
                "elapsed_time": {
                    "system_time": self.system_time.elapsed_time,
                    "ros_time": self.ros_time.elapsed_time,
                },
                "time_mode": self.time_mode,
                "time_max": self.time_max,
                "lap_count": self.lap_count,
                "recovery_count": self.recovery_count,
                "courseout_count": self.courseout_count,
                "is_courseout": self.is_courseout,
                "judgestate": self.judgestate,
            },
            "debug_info": {
                "description": "debug information",
            },
        }
        return json

    def writeResult(self):
        ## For Debug, output Result file.
        script_dir = os.path.dirname(os.path.abspath(__file__))
        log_file_path = script_dir + "/log/" + "game_result.log"
        with open(log_file_path, "w") as f:
            jsondata = self.getGameStateJson()
            json.dump(jsondata, f)
            app.logger.info("Write Result {}".format(jsondata))
            print("result log: " + log_file_path)
            pprint.pprint(jsondata, compact = True)

### API definition
@app.route('/')
def index():
    ip = request.remote_addr
    app.logger.info("GET /(root) "+ str(ip))
    return render_template('index.html')

#@app.route('/favicon.ico')
#def favicon():
#    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='static/')

@app.route('/judgeserver/request', methods=['POST'])
def requestToJudge():
    print("request to POST /judgeserver/request")
    body = request.json
    ip = request.remote_addr
    app.logger.info("POST /judgeserver/request " + str(ip) + str(body))
    response = GameManager.requestToServer(body)
    res = response
    app.logger.info("RESPONSE /judgeserver/request " + str(ip) + str(res))
    return jsonify(res)

@app.route('/judgeserver/updateData', methods=['POST'])
def updateData():
    #print("request to POST /judgeserver/updateData")
    body = request.json
    ip = request.remote_addr
    app.logger.info("POST /judgeserver/updateData " + str(ip) + str(body))
    response = GameManager.updateData(body)
    res = response
    app.logger.info("RESPONSE /judgeserver/updateData " + str(ip) + str(res))
    return jsonify(res)

@app.route('/judgeserver/getState', methods=['GET'])
def getState():
    #print("request to GET /judgeserver/getState")
    ip = request.remote_addr
    #app.logger.info("GET /judgeserver/getState " + str(ip))
    state_json = GameManager.getGameStateJson()
    res = state_json
    #app.logger.info("RESPONSE /judgeserver/getState "+ str(ip) + str(res))
    return jsonify(res)

def parse_argument():
    # argument parse
    parser = argparse.ArgumentParser(description='judger server')
    parser.add_argument('--gametime', '--gt', default=int(DEFAULT_GAME_TIME), type=int, help='game time [sec]')
    parser.add_argument('--timemode', '--tm', default=int(DEFAULT_TIME_MODE), type=int, help='time mode (1:SYSTEM_TIME/2:ROS_TIME)')
    args = parser.parse_args()
    return args

if __name__ == '__main__':
    # global object judge
    GameManager = GameManagerClass(parse_argument())

    # app for debug
    #now = datetime.datetime.now()
    #now_str = now.strftime("%y%m%d_%H%M%S")
    #script_dir = os.path.dirname(os.path.abspath(__file__))
    #log_file_path = script_dir + "/log/" + now_str + ".log"
    #handler = RotatingFileHandler("/dev/null")
    #handler = RotatingFileHandler(log_file_path, maxBytes = 1000000, backupCount=100)
    #handler.setLevel(logging.INFO)
    #app.logger.setLevel(logging.INFO)
    #app.logger.addHandler(handler)
    l = logging.getLogger()
    l.addHandler(logging.FileHandler("/dev/null"))
    app.run(debug=True, host='0.0.0.0', port=5000)
    #app.run(debug=False, host='0.0.0.0', port=5000)
