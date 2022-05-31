# imports for file path handling
import os
import sys
from pathlib import Path
from ROAR.agent_module import agent
sys.path.append(Path(os.getcwd()).parent.as_posix())
from ROAR.configurations.configuration import Configuration as AgentConfig
import gym
import torch as th
from torch import nn
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from ROAR.planning_module.mission_planner.waypoint_following_mission_planner import WaypointFollowingMissionPlanner
from pathlib import Path
from ROAR.utilities_module.occupancy_map import OccupancyGridMap
from ROAR.agent_module.agent import Agent
from ROAR.utilities_module.vehicle_models import Vehicle, VehicleControl
import numpy as np
from ROAR.utilities_module.data_structures_models import Transform, Location
import cv2
from typing import Optional
import scipy.stats
from collections import deque
from stable_baselines3.ppo.ppo import PPO
from ppo_util import find_latest_model, CustomMaxPoolCNN, Atari_PPO_Adapted_CNN


# def layer_init(layer, std=np.sqrt(2), bias_const=0.0):
#     th.nn.init.orthogonal_(layer.weight, std)
#     th.nn.init.constant_(layer.bias, bias_const)
#     return layer
#
# class Atari_PPO_Adapted_CNN(BaseFeaturesExtractor):
#     """
#     Based on https://github.com/DarylRodrigo/rl_lib/blob/master/PPO/Models.py
#     """
#     def __init__(self, observation_space: gym.spaces.Box, features_dim: int = 256):
#         super(Atari_PPO_Adapted_CNN, self).__init__(observation_space,features_dim)
#         channels = observation_space.shape[0]*observation_space.shape[1]
#         self.network = nn.Sequential(
#             # Scale(1/255),
#             layer_init(nn.Conv2d(channels, 32, 8, stride=4)),
#             nn.ReLU(),
#             layer_init(nn.Conv2d(32, 64, 4, stride=2)),
#             nn.ReLU(),
#             layer_init(nn.Conv2d(64, 64, 3, stride=1)),
#             nn.ReLU(),
#             nn.Flatten(),
#             layer_init(nn.Linear(3136, features_dim)),
#             # nn.ReLU(),
#         )
#
#     def forward(self, observations: th.Tensor) -> th.Tensor:
#         observations=observations.view(observations.shape[0],-1,*observations.shape[3:])
#         return self.network(observations)



mode='baseline'
if mode=='no_map':
    FRAME_STACK = 1
else:
    FRAME_STACK = 4

if mode=='baseline':
    CONFIG = {
        "x_res": 84,
        "y_res": 84
    }
else:
    CONFIG = {
        # max values are 280x280
        # original values are 80x80
        "x_res": 80,
        "y_res": 80
    }



class RLe2ePPOEvalAgent(Agent):

    def __init__(self, vehicle: Vehicle, agent_settings: AgentConfig, **kwargs):
        super().__init__(vehicle, agent_settings, **kwargs)

        self.i = 0

        self.agent_config = agent_settings

        policy_kwargs = dict(
            features_extractor_class=Atari_PPO_Adapted_CNN,
            features_extractor_kwargs=dict(features_dim=256)
        )

        spawn_params = {
            "num_spawn_pts": 13,  # Last one is 12
            "init_spawn_pt": 12,
            "dynamic_spawn": False,  # True if start at different spawn locations on reset

            # Spawn Guide:
            # 1 = Roundabout
            # 5 = Sharpest Turn
            # 8 = Leap of Faith (Height of Leap is roughly 360)
            # 12 = "Race Start"

            # Dynamic Type Choice:
            #   1. "uniform random" - Choose from uniform random distribution in range(init_spawn_point:num_spawn_pts)
            #   2. "linear forward" - After reset spawn point increments by one. Loops back to init after num_spawn_pts reached
            #   3. "linear backward" - After reset decrement spawn point by one. Loops back to num_spawn_pts after init reached
            #   4. "custom spawn pts" - Provide a custom list of spawn points.
            "dynamic_type": "uniform random",
            "custom_list": [4, 9, 0, 12, 7],  # List of custom spawn pts

            "spawn_pt_iterator": 0,  # DO NOT TOUCH THIS! Used Internally!
            "spawn_int_map": [91, 0, 140, 224, 312, 442, 556, 730, 782, 898, 1142, 1283, 39],
        }

        #print(self.model_path)
        misc_params = {
            "env_name": 'roar-e2e-ppo-v0',
            "run_fps": 8,  # TODO Link to the environment RUN_FPS
            "model_directory": Path("./output/PPOe2e_Major_FC_Run_1"),
            "run_name": "Major FC Run 1",
            "total_timesteps": int(1e6),
        }
        PPO_params = dict(
            learning_rate=0.00001,  # be smaller 2.5e-4
            n_steps=1024 * misc_params["run_fps"],
            batch_size=64,  # mini_batch_size = 256?
            # n_epochs=10,
            gamma=0.99,  # rec range .9 - .99
            ent_coef=.00,  # rec range .0 - .01
            # gae_lambda=0.95,
            # clip_range_vf=None,
            # vf_coef=0.5,
            # max_grad_norm=0.5,
            # use_sde=True,
            # sde_sample_freq=5,
            # target_kl=None,
            # tensorboard_log=(Path(misc_params["model_directory"]) / "tensorboard").as_posix(),
            # create_eval_env=False,
            # policy_kwargs=None,
            verbose=1,
            seed=1,
            device=th.device('cuda:0' if th.cuda.is_available() else 'cpu'),
            # _init_setup_model=True,
        )
        training_kwargs = PPO_params
        MODEL_DIR = misc_params["model_directory"]
        self.model_path = Path("C:/Users/roar/Documents/ROAR_RL_MENG_team/ROAR/ROAR_gym/output/PPOe2e_Major_FC_Run_1/logs/rl_model_10749313_steps.zip")
        if self.model_path == None:
            self.model_path = Path(find_latest_model(MODEL_DIR))
        self.model = PPO.load(Path(self.model_path), **training_kwargs)

        ######## initilization from agent ##################
        self.mission_planner = WaypointFollowingMissionPlanner(agent = self)
        self.flatten = True
        self.occupancy_map = OccupancyGridMap(agent = self, threaded=True)
        occ_file_path = Path("C:/Users/roar/Documents/ROAR_RL_MENG_team/ROAR/ROAR_Sim/data/final3.npy")
        self.occupancy_map.load_from_file(occ_file_path)
        self.plan_lst = list(self.mission_planner.produce_single_lap_mission_plan())
        self.kwargs = kwargs
        self.interval = self.kwargs.get('interval', 20)
        self.look_back = self.kwargs.get('look_back', 5)
        self.look_back_max = self.kwargs.get('look_back_max', 10)
        self.thres = self.kwargs.get('thres', 1e-3)

        if self.flatten:
            self.bbox_reward_list=[0.499 for _ in range(20)]
        else:
            middle=scipy.stats.norm(20//2, 20//3).pdf(20//2)
            self.bbox_reward_list=[scipy.stats.norm(20//2, 20//3).pdf(i)/middle*0.5 for i in range(20)]

        self.spawn_counter = 0
        self.int_counter = self.spawn_counter
        self.cross_reward=0
        self.counter = 0
        self.finished = False
        # self.curr_dist_to_strip = 0
        self.bbox: Optional[LineBBox] = None
        self.bbox_list = []# list of bbox
        self.frame_queue = deque([None, None, None], maxlen=4)
        self.vt_queue = deque([None, None, None], maxlen=4)
        #self._get_next_bbox()
        self._get_all_bbox()
        # self.occupancy_map.draw_bbox_list(self.bbox_list)
        for _ in range(4):
            self.bbox_step()
        self.finish_loop = False
        ##############################################################

        ############## initilization from environment ################
        # self.prev_speed = 0
        # self.crash_check = False
        # self.speeds = []
        # self.prev_int_counter = 0
        self.steps = 0
        # self.largest_steps = 0
        # self.highspeed = 0
        # self.complete_loop = False
        # self.time_to_waypoint_ratio = 0.25
        # self.fps = 8
        # self.death_line_dis = 5
        # self.stopped_counter = 0
        # self.stopped_max_count = 100
        self.speed = 0
        self.current_hs = 0

        # # used to check laptime
        # if self.carla_runner.world is not None:
        #     self.last_sim_time = self.carla_runner.world.hud.simulation_time
        # else:
        #     self.last_sim_time = 0
        # self.sim_lap_time = 0

        self.deadzone_trigger = False
        self.deadzone_level = 0.001
        self.overlap = False

        # Spawn initializations
        # TODO: This is a hacky fix because the reset function seems to be called on init as well.
        spawn_int_map = np.array([91, 0, 140, 224, 312, 442, 556, 730, 782, 898, 1142, 1283, 39])
        if spawn_params["dynamic_type"] == "linear forward":
            self.agent_config.spawn_point_id = spawn_params["init_spawn_pt"] - 1
        elif spawn_params["dynamic_type"] == "linear backward":
            self.agent_config.spawn_point_id = spawn_params["init_spawn_pt"] + 1
        else:
            self.agent_config.spawn_point_id = spawn_params["init_spawn_pt"]

        self.spawn_counter = spawn_int_map[self.agent_config.spawn_point_id]
        print("#########################\n",self.spawn_counter)

       

        self.deadzone_trigger = True
        self.deadzone_level = 0.001

    def reset(self,vehicle: Vehicle):
        self.vehicle=vehicle
        self.int_counter = 0
        self.cross_reward=0
        self.counter = 0
        self.finished = False
        self.bbox: Optional[LineBBox] = None
        self.frame_queue = deque([None, None, None], maxlen=4)
        self.vt_queue = deque([None, None, None], maxlen=4)
        for _ in range(4):
            self.bbox_step()
        self.finish_loop=False

    def run_step(self, vehicle: Vehicle, sensors_data = None, update_queue = True) -> VehicleControl:
        
        # agent steps
        self.vehicle = vehicle
        self.bbox_step(update_queue)
        
        
        obs = self._get_obs()

        #print("##############################")
        #print(obs)
        action, next_obs = self.model.predict(obs,deterministic=False)
        #print(self.i, action)
        self.i += 1
        # if self.i ==20:
        #     exit()
        # env steps
        self.steps += 1
        for i in range(1):
            action = np.reshape(action, (-1))
            check = (action[i * 3 + 0] + 0.5) / 2 + 1
            if check > 0.5:
                throttle = 0.7
                braking = 0
            else:
                throttle = 0
                braking = .8

            steering = action[i * 3 + 1] / 5

            if self.deadzone_trigger and abs(steering) < self.deadzone_level:
                steering = 0.0

        self.speed = self.vehicle.get_speed(self.vehicle)
        if self.speed > self.current_hs:
            self.current_hs = self.speed

        return VehicleControl(throttle=throttle, steering=steering, braking=braking)


    def bbox_step(self, update_queue = True):
        """
        This is the function that the line detection agent used
        Main function to use for detecting whether the vehicle reached a new strip in
        the current step. The old strip (represented as a bbox) will be gone forever
        return:
        crossed: a boolean value indicating whether a new strip is reached
        dist (optional): distance to the strip, value no specific meaning
        self.counter += 1
        if not self.finished:
            while(True):
                crossed, dist = self.bbox.has_crossed(self.vehicle.transform)
                if crossed:
                    self.int_counter += 1
                    self.cross_reward+=crossed
                    self._get_next_bbox()
                else:
                    break

            return dist
        return False, 0.0
        """
        if self.int_counter >= len(self.bbox_list):
            self.finish_loop=True
        currentframe_crossed = []

        while(self.vehicle.transform.location.x!=0):
            crossed, dist = self.bbox_list[self.int_counter%len(self.bbox_list)].has_crossed(self.vehicle.transform)
            if crossed:
                self.cross_reward+=crossed
                currentframe_crossed.append(self.bbox_list[self.int_counter%len(self.bbox_list)])
                self.int_counter += 1
            else:
                break
        if self.vehicle.transform.location != Location(x=0.0, y=0.0, z=0.0):
            if update_queue:
                if len(self.frame_queue) < 4 and len(currentframe_crossed):
                    self.frame_queue.append(currentframe_crossed)
                elif len(currentframe_crossed):
                    self.frame_queue.popleft()
                    self.frame_queue.append(currentframe_crossed)
                else:
                    self.frame_queue.append(None)
                # add vehicle tranform
                if len(self.vt_queue) < 4:
                    self.vt_queue.append(self.vehicle.transform)
                else:
                    
                    self.vt_queue.popleft()
                    self.vt_queue.append(self.vehicle.transform)
            else:
                if self.frame_queue[-1]==None:
                    self.frame_queue[-1]=currentframe_crossed
                else:
                    self.frame_queue[-1].extend(currentframe_crossed)

    def _get_all_bbox(self):
        local_int_counter = 0
        curr_lb = self.look_back
        curr_idx = local_int_counter * self.interval
        while curr_idx + curr_lb < len(self.plan_lst):
            if curr_lb > self.look_back_max:
                local_int_counter += 1
                curr_lb = self.look_back
                curr_idx = local_int_counter * self.interval
                continue

            t1 = self.plan_lst[curr_idx]
            t2 = self.plan_lst[curr_idx + curr_lb]

            dx = t2.location.x - t1.location.x
            dz = t2.location.z - t1.location.z
            if abs(dx) < self.thres and abs(dz) < self.thres:
                curr_lb += 1
            else:
                self.bbox_list.append(LineBBox(t1, t2, self.bbox_reward_list,self.flatten))
                local_int_counter += 1
                curr_lb = self.look_back
                curr_idx = local_int_counter * self.interval
        # no next bbox
        # print("finished all the iterations!")
        #self.finished = True

    def _get_next_bbox(self):
        # make sure no index out of bound error
        curr_lb = self.look_back
        curr_idx = (self.int_counter%len(self.bbox_list)) * self.interval
        while curr_idx + curr_lb < len(self.plan_lst):
            if curr_lb > self.look_back_max:
                self.int_counter += 1
                curr_lb = self.look_back
                curr_idx = (self.int_counter%len(self.bbox_list)) * self.interval
                continue

            t1 = self.plan_lst[curr_idx]
            t2 = self.plan_lst[curr_idx + curr_lb]

            dx = t2.location.x - t1.location.x
            dz = t2.location.z - t1.location.z
            if abs(dx) < self.thres and abs(dz) < self.thres:
                curr_lb += 1
            else:
                self.bbox = LineBBox(t1, t2,self.bbox_reward_list,self.flatten)
                return
        # no next bbox
        print("finished all the iterations!")
        self.finished = True

    def _get_obs(self) -> np.ndarray:
        if mode=='baseline':
            index_from=(self.int_counter%len(self.bbox_list))
            if index_from+10<=len(self.bbox_list):
                # print(index_from,len(self.agent.bbox_list),index_from+10-len(self.agent.bbox_list))
                next_bbox_list=self.bbox_list[index_from:index_from+10]
            else:
                # print(index_from,len(self.agent.bbox_list),index_from+10-len(self.agent.bbox_list))
                next_bbox_list=self.bbox_list[index_from:]+self.bbox_list[:index_from+10-len(self.bbox_list)]
            assert(len(next_bbox_list)==10)
            #import pdb
            #pdb.set_trace()
            map_list,overlap = self.occupancy_map.get_map_baseline(transform_list=self.vt_queue,
                                                    view_size=(CONFIG["x_res"], CONFIG["y_res"]),
                                                    bbox_list=self.frame_queue,
                                                                 next_bbox_list=next_bbox_list
                                                    )
            self.overlap=overlap
            cv2.imshow("data", np.hstack(np.hstack(map_list))) # uncomment to show occu map
            cv2.waitKey(1)

            return map_list[:,:-1]
        else:
            data = self.occupancy_map.get_map(transform=self.vehicle.transform,
                                                    view_size=(CONFIG["x_res"], CONFIG["y_res"]),
                                                    arbitrary_locations=self.bbox.get_visualize_locs(),
                                                    arbitrary_point_value=self.bbox.get_value(),
                                                    vehicle_velocity=self.vehicle.velocity,
                                                    # rotate=self.agent.bbox.get_yaw()
                                                    )
            # data = cv2.resize(occu_map, (CONFIG["x_res"], CONFIG["y_res"]), interpolation=cv2.INTER_AREA)
            #cv2.imshow("Occupancy Grid Map", cv2.resize(np.float32(data), dsize=(500, 500)))

            # data_view=np.sum(data,axis=2)
            cv2.imshow("data", data) # uncomment to show occu map
            cv2.waitKey(1)
            # yaw_angle=self.agent.vehicle.transform.rotation.yaw
            # velocity=self.agent.vehicle.get_speed(self.agent.vehicle)
            # data[0,0,2]=velocity
            data_input=data.copy()
            data_input[data_input==1]=-10
            return data_input  # height x width x 3 array


class LineBBox(object):
    def __init__(self, transform1: Transform, transform2: Transform,bbox_reward_list,flatten) -> None:
        self.x1, self.z1 = transform1.location.x, transform1.location.z
        self.x2, self.z2 = transform2.location.x, transform2.location.z
        #print(self.x2, self.z2)
        self.pos_true = True
        self.thres = 1e-2
        self.eq = self._construct_eq()
        self.dis = self._construct_dis()
        self.strip_list = None
        self.size=20
        self.bbox_reward_list=bbox_reward_list
        self.strip_list = None
        self.generate_visualize_locs(20)
        self.flatten=flatten

        if self.eq(self.x1, self.z1) > 0:
            self.pos_true = False

    def _construct_eq(self):
        dz, dx = self.z2 - self.z1, self.x2 - self.x1

        if abs(dz) < self.thres:
            def vertical_eq(x, z):
                return x - self.x2

            return vertical_eq
        elif abs(dx) < self.thres:
            def horizontal_eq(x, z):
                return z - self.z2

            return horizontal_eq

        slope_ = dz / dx
        self.slope = -1 / slope_
        # print("tilted strip with slope {}".format(self.slope))
        self.intercept = -(self.slope * self.x2) + self.z2

        def linear_eq(x, z):
            return z - self.slope * x - self.intercept

        return linear_eq

    def _construct_dis(self):
        dz, dx = self.z2 - self.z1, self.x2 - self.x1

        if abs(dz) < self.thres:
            def vertical_dis(x, z):
                return z - self.z2

            return vertical_dis
        elif abs(dx) < self.thres:
            def horizontal_dis(x, z):
                return x - self.x2

            return horizontal_dis

        slope_ = dz / dx
        self.slope = -1 / slope_
        # print("tilted strip with slope {}".format(self.slope))
        self.intercept = -(self.slope * self.x2) + self.z2

        def linear_dis(x, z):
            z_diff=z - self.z2
            x_diff=x - self.x2
            dis=np.sqrt(np.square(z_diff)+np.square(x_diff))
            angle1=np.abs(np.arctan(slope_))
            angle2=np.abs(np.arctan(z_diff/x_diff))
            return dis*np.sin(np.abs(angle2-angle1))

        return linear_dis

    def has_crossed(self, transform: Transform):
        x, z = transform.location.x, transform.location.z
        dist = self.eq(x, z)
        crossed=dist > 0 if self.pos_true else dist < 0
        if self.flatten:
            return (crossed,dist)
        else:
            middle=scipy.stats.norm(self.size//2, self.size//2).pdf(self.size//2)
            return (scipy.stats.norm(self.size//2, self.size//2).pdf(self.size//2-self.dis(x, z))/middle if crossed else 0, dist)

    def generate_visualize_locs(self, size=10):
        if self.strip_list is not None:
            return self.strip_list

        name = self.eq.__name__
        if name == 'vertical_eq':
            xs = np.repeat(self.x2, size)
            zs = np.arange(self.z2 - (size // 2), self.z2 + (size // 2))
        elif name == 'horizontal_eq':
            xs = np.arange(self.x2 - (size // 2), self.x2 + (size // 2))
            zs = np.repeat(self.z2, size)
        else:
            range_ = size * np.cos(np.arctan(self.slope))
            xs = np.linspace(self.x2 - range_ / 2, self.x2 + range_ / 2, num=size)
            zs = self.slope * xs + self.intercept
            # print(np.vstack((xs, zs)).T)

        #         self.strip_list = np.vstack((xs, zs)).T
        self.strip_list = []
        for i in range(len(xs)):
            self.strip_list.append(Location(x=xs[i], y=0, z=zs[i]))

    def get_visualize_locs(self):
        return self.strip_list

    def get_value(self):
        return self.bbox_reward_list

    def get_directional_velocity(self,x,y):
        dz, dx = self.z2 - self.z1, self.x2 - self.x1
        dx,dz=[dx,dz]/np.linalg.norm([dx,dz])
        return dx*x+dz*y

    def to_array(self,x,z):
        dz, dx = self.z2 - self.z1, self.x2 - self.x1
        angle1=np.arctan2(-dx,-dz)/np.pi

        dz, dx = self.z2 - z, self.x2 - x
        angle2=np.arctan2(-dx,-dz)/np.pi
        return np.array([dx, dz, np.sqrt(np.square(dz)+np.square(dx)),angle1,angle2])

    def get_yaw(self):
        dz, dx = self.z2 - self.z1, self.x2 - self.x1
        angle=np.arctan2(-dx,-dz)/np.pi*180
        return angle