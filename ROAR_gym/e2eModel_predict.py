"""
IMPORTANT
IF YOU HAVE NOT RUN THIS FILE AS 'ADMIN' (OR OPENED PYCHARM AS 'ADMIN')
STOP AND RESTART WITH ADMIN PRIVILEGES

TODO: Before Running this file make the following changes:
1. Add the following line:
    self._last_obs = np.nan_to_num(self._last_obs)

to the following file:
    ROAR\venv\Lib\site-packages\stable_baselines3\common\on_policy_algorithm.py

2. Add this line after line 167 such that:
with th.no_grad():
    # Convert to pytorch tensor or to TensorDict
    self._last_obs = np.nan_to_num(self._last_obs)
    obs_tensor = obs_as_tensor(self._last_obs, self.device)
    actions, values, log_probs = self.policy.forward(obs_tensor)

3. Add: #############################################################################still needed?###########

        data.pop('_last_obs')

    in  line 652 of base_class.py for sb3
    possible location of file: \envs\ROAR\Lib\site-packages\stable_baselines3\common\base_class.py

4. Change for on_policy_algorithm.py, in function collect_rollouts add:

        self.env.reset()

    before the following while loop:

        while n_steps < n_rollout_steps:
"""

# IMPORTS
# imports for logs and warnings
import warnings
import logging

from typing import Optional, Dict

# imports for weights and biases integration
import wandb
from wandb.integration.sb3 import WandbCallback

# imports for file path handling
import os
import sys
from pathlib import Path
sys.path.append(Path(os.getcwd()).parent.as_posix())

# imports for reading and writing json config files
import json

# imports from the ROAR module
from ROAR_Sim.configurations.configuration import Configuration as CarlaConfig
from ROAR.configurations.configuration import Configuration as AgentConfig
from ROAR.agent_module.agent import Agent
from ROAR.agent_module.rl_e2e_ppo_agent import RLe2ePPOAgent
from ROAR.agent_module.forward_only_agent import ForwardOnlyAgent   # testing stuff

# imports for reinforcement learning
import gym
import torch as th
from stable_baselines3.ppo.ppo import PPO
from stable_baselines3.ppo.policies import CnnPolicy
from stable_baselines3.common.callbacks import CheckpointCallback, EveryNTimesteps, CallbackList, BaseCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, VecVideoRecorder


# imports for helper functions and torch cnn models
from ppo_util import find_latest_model, CustomMaxPoolCNN, Atari_PPO_Adapted_CNN



# imports from config files
from configurations.ppo_configuration import PPO_params, misc_params#, wandb_saves
agent_config = AgentConfig.parse_file(Path("configurations/agent_configuration.json"))
carla_config = CarlaConfig.parse_file(Path("configurations/carla_configuration.json"))

# Setup for the loggers
logging.getLogger("tensorflow").setLevel(logging.ERROR)
logging.getLogger("numpy").setLevel(logging.ERROR)
warnings.filterwarnings('ignore')
try:
    from ROAR_Gym.envs.roar_env import LoggingCallback
except:
    from ROAR_Gym.ROAR_Gym.envs.roar_env import LoggingCallback

# os.environ["CUDA_VISIBLE_DEVICES"]="0,1"
#  Parameters & Constants
CUDA_VISIBLE_DEVICES = 1
RUN_FPS = misc_params["run_fps"]
MODEL_DIR = misc_params["model_directory"]
# WANDB_CONFIG_DIR = "configurations/wandb_configuration.json"


def json_read_write(file, load_var=None, mode='r'):
    """

    Args:
        file: address of json file to be loaded
        load_var: variable to be written to, or read from
        mode: 'r' to read from json, 'w' to write to json

    Returns:
        load_var: variable with data that has been read in mode 'r'
                  original variable in case of 'w'

    """
    if mode == 'r':
        with open(file, mode) as json_file:
            load_var = json.load(json_file)  # Reading the file
            print(f"{file} json config read successful")
            json_file.close()
            return load_var
    elif mode == 'w':
        assert load_var is not None, "load_var was None"
        with open(file, mode) as json_file:
            json.dump(load_var, json_file)  # Writing to the file
            print(f"{file} json config write successful")
            json_file.close()
            return load_var
    else:
        assert mode == 'w' or 'r', f"unsupported mode type: {mode}"
        return None


class Tensorboard_Faster_Logger(BaseCallback):
    """
    Callback for saving a model (the check is done every ``check_freq`` steps)
    based on the training reward (in practice, we recommend using ``EvalCallback``).

    :param check_freq:
    :param log_dir: Path to the folder where the model will be saved.
      It must contains the file created by the ``Monitor`` wrapper.
    :param verbose: Verbosity level.
    """
    def __init__(self, check_freq: int, verbose: int = 1):
        super(Tensorboard_Faster_Logger, self).__init__(verbose)
        self.check_freq = check_freq

    # def _init_callback(self) -> None:

    def _on_step(self) -> bool:
        if self.n_calls % self.check_freq == 0:
            self.logger.dump(self.num_timesteps)
        return True


def main(pass_num):
    # Create the gym environment using the configs
    env = gym.make(
        id=misc_params["env_name"],
        params={
            "agent_config": agent_config,
            "carla_config": carla_config,
            "ego_agent_class": RLe2ePPOAgent,
        }
    )
    #print(th.cuda.is_available())

    # Setting the feature extract or based on the environment mode
    if env.mode == 'baseline':
        policy_kwargs = dict(
            features_extractor_class=Atari_PPO_Adapted_CNN,
            features_extractor_kwargs=dict(features_dim=256)
        )
    else:
        policy_kwargs = dict(
            features_extractor_class=CustomMaxPoolCNN,
            features_extractor_kwargs=dict(features_dim=256)
        )

    # training kwargs for PPO init
    training_kwargs = PPO_params

    # Try to find latest model path if we have trained previously
    latest_model_path = find_latest_model(MODEL_DIR)
    print(latest_model_path)
    # FIXME wandb may continue old run if the run crashes before it is logged
    if latest_model_path is None:
        model = PPO(
            CnnPolicy,
            env=env,
            policy_kwargs=policy_kwargs,
            # tensorboard_log=f"runs/{run.name}",  # TODO add "tensorboard" to logdir name
            **training_kwargs
        )

        # print(f"Starting new run {run.id}")
    else:
        # Load wandb run
        # run = wandb_run_init(
        #     wandb_hp_config,
        #     load=True,
        # )

        # Load the model
        #model_path = "C:/Users/micha/Desktop/ROAR_MEng/ROAR/ROAR_gym/output/PPOe2e_FullControl_Run_8/logs/rl_model_13737636_steps"
        #model = PPO.load(Path(model_path))
        model = PPO.load(
            latest_model_path,
            env=env,
            policy_kwargs=policy_kwargs,
            # tensorboard_log=f"runs/{run.name}",  # TODO add "tensorboard" to logdir name
            **training_kwargs,
        )

        # print(f"Loading old run {run.id}")

    print("Model Loaded Successfully")

    # Defining Callback Functions

    logging_callback = LoggingCallback(model=model)

    # faster_Logging_Callback = Tensorboard_Faster_Logger(check_freq=wandb_saves["model_save_freq"])

    # checkpoint_callback = CheckpointCallback(
    #     save_freq=wandb_saves["model_save_freq"],
    #     verbose=2,
    #     save_path=(MODEL_DIR / "logs").as_posix()
    # )

    # event_callback = EveryNTimesteps(
    #     n_steps=wandb_saves["model_save_freq"],
    #     callback=checkpoint_callback
    # )

    # wandb_callback = WandbCallback(
    #     verbose=2,
    #     model_save_path=f"models/{run.id}",
    #     gradient_save_freq=PPO_params["n_steps"],
    #     model_save_freq=wandb_saves["model_save_freq"],
    # )

    callbacks = CallbackList([
        # wandb_callback,
        # checkpoint_callback,
        # event_callback,
        logging_callback
        # faster_Logging_Callback
    ])

    # Begin learning
    # model = model.learn(
    #     total_timesteps=misc_params["total_timesteps"],
    #     callback=callbacks,
    #     reset_num_timesteps=False,
    #     # tb_log_name=wandb_config["run_id"],
    # )

    obs = env.reset()
    i = 0
    while True:
        print("##############################")
        #print(obs)
        action, _states = model.predict(obs)
        print(i, action)
        i += 1
        # if i ==20:
        #     exit()
        obs, rewards, dones, info = env.step(action)
        env.render()

    # Save Model
    #model.save(MODEL_DIR / f"roar_e2e_model_{pass_num}")  # TODO fix naming convention
    #print("Successful Save!")
    # # Finish wandb run
    # run.finish()

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        datefmt="%H:%M:%S", level=logging.INFO)
    logging.getLogger("Controller").setLevel(logging.ERROR)
    logging.getLogger("SimplePathFollowingLocalPlanner").setLevel(logging.ERROR)
    i=0
    while True:
        main(i)
        i += 1




















