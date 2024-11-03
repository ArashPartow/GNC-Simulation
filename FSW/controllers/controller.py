import configparser
import numpy as np
from world.math.quaternions import *
from FSW.controllers.detumbling_controller import *

class Controller:
    def __init__(self, config, Magnetorquers, Idx) -> None:
        self.config = config
        self.pointing_mode    = config["pointing_mode"]
        self.pointing_target  = config["pointing_target"]
        self.controller_algo  = config["algorithm"]
        self.tgt_ang_vel      = np.array(config["tgt_ang_vel"], dtype=np.float64)
        self.feedback_gains   = np.array(config["state_feedback_gains"], dtype=np.float64)
        self.est_world_states = None
        self.mtb              = Magnetorquers
        self.G_mtb_b = np.array(config["mtb_orientation"]).reshape(config["N_mtb"], 3)
        self.G_rw_b  = np.array(config["rw_orientation"]).reshape(config["N_rw"], 3)
        self.inertia = np.array(config["inertia"]).reshape(3,3)
        self.Bcrossctr  = BcrossController(self.G_mtb_b,
                                            config["bcrossgain"],
                                            Magnetorquers,
                                            self.inertia,
                                            config["tgt_ang_vel"])
        self.lyapsunpointctr = LyapBasedSunPointingController(self.inertia, 
                                                              self.G_mtb_b,
                                                              config["bcrossgain"],
                                                              config["tgt_ang_vel"],
                                                              Magnetorquers)
        self.basesunpointctr = BaselineSunPointingController(self.inertia, 
                                                              self.G_mtb_b,
                                                              config["bcrossgain"],
                                                              config["tgt_ang_vel"],
                                                              Magnetorquers)

        self.allocation_mat = np.zeros((Idx["NU"],3))
       
    def _load_gains(self):
        gains = {}
        if 'Gains' in self.config:
            for key in self.config['Gains']:
                gains[key] = float(self.config['Gains'][key])
        return gains
    
    # define feedforward torque and state profile
    def define_att_profile(self, date, pointing_mode, pointing_target, tgt_ang_vel, est_world_states):
        ref_ctrl_states = np.zeros((7,))
        
        if pointing_target == "Sun":
            # Define reference torque as zero
            ref_torque = np.zeros((3,))
            
            # Define reference control states with constant estimated sun direction
            # quaternion defining sun pointing direction
            # +z pointing to self.state[13:16]
            # +x cross product of +z and [0,0,1]
            # +y completes the right handed coordinate system
            z_body = -est_world_states[13:16] / np.linalg.norm(est_world_states[13:16])
            x_body = np.cross(z_body, np.array([0,0,1]))
            y_body = np.cross(z_body, x_body)
            Rot_mat = np.vstack((x_body, y_body, z_body)).T
            q_ref = rotmat2quat(Rot_mat)
        elif pointing_target == "Nadir":
            att_states = est_world_states[6:13]
            # Default values if not sun pointing
            ref_ctrl_states = np.zeros((19,))
            ref_torque = np.zeros((3,))
            
        if  pointing_mode == "detumble":
            # Default values if not sun pointing
            ref_ctrl_states = np.zeros((19,))
            ref_torque = np.zeros((3,))
        elif pointing_mode == "spin-stabilized":
            # Default values if not sun pointing
            ref_ctrl_states = np.zeros((19,))
            # reference angular velocity in pointing axis 
            ref_ctrl_states[:4]  = q_ref
            ref_ctrl_states[4:7] = tgt_ang_vel
            ref_torque = np.zeros((3,))
        elif pointing_mode == "3D-stabilized":
            q_ref = rotmat2quat(Rot_mat)
            ref_ctrl_states[:4] = q_ref
            ref_torque = np.zeros((3,))
        else:
            raise ValueError(f"Unrecognized pointing mode: {pointing_mode}")
            
        return ref_torque, ref_ctrl_states
    
    def get_torque(self, date, ref_torque, ref_ctrl_states, est_ctrl_states, Idx):
        # from the reference and estimated quaternions, get the error quaternion for control
        if self.controller_algo == "Bcross":
            Re2b = quatrotation(est_ctrl_states[Idx["X"]["QUAT"]]).T
            bfMAG_FIELD = Re2b @ est_ctrl_states[Idx["X"]["MAG_FIELD"]]
            return self.Bcrossctr.get_dipole_moment_command(bfMAG_FIELD, 
                                                            est_ctrl_states[Idx["X"]["ANG_VEL"]])
        elif self.controller_algo == "Lyapunov":
            Re2b = quatrotation(est_ctrl_states[Idx["X"]["QUAT"]]).T
            magnetic_field   = Re2b @ est_ctrl_states[Idx["X"]["MAG_FIELD"]]
            angular_velocity = est_ctrl_states[Idx["X"]["ANG_VEL"]]
            ref_angular_velocity = ref_ctrl_states[4:7]
            sun_vector       = Re2b @ est_ctrl_states[Idx["X"]["SUN_POS"]]
            sun_vector       = sun_vector / np.linalg.norm(sun_vector)
            return self.lyapsunpointctr.get_dipole_moment_command(magnetic_field, angular_velocity,
                                                                  ref_angular_velocity, sun_vector) 
        elif self.controller_algo == "BaseSP":
            Re2b = quatrotation(est_ctrl_states[Idx["X"]["QUAT"]]).T
            magnetic_field   = Re2b @ est_ctrl_states[Idx["X"]["MAG_FIELD"]]
            angular_velocity = est_ctrl_states[Idx["X"]["ANG_VEL"]]
            ref_angular_velocity = ref_ctrl_states[4:7]
            sun_vector       = Re2b @ est_ctrl_states[Idx["X"]["SUN_POS"]]
            sun_vector       = sun_vector / np.linalg.norm(sun_vector)
            return self.basesunpointctr.get_dipole_moment_command(magnetic_field, angular_velocity,
                                                                  ref_angular_velocity, sun_vector) 
        q_ref = ref_ctrl_states[:4]
        q_est = est_ctrl_states[Idx["X"]["QUAT"]]
        q_err = hamiltonproduct(q_ref, q_inv(q_est))
        err_vec = np.hstack((q_err[1:], ref_ctrl_states[4:7] - est_ctrl_states[Idx["X"]["ANG_VEL"]]))
        
        torque = ref_torque + self.feedback_gains @ err_vec
        return torque
    
    def allocate_torque(self, state, torque_cmd, Idx):
        # Placeholder for actuator management
        # if torque = B @ actuator_cmd
        # actuator_cmd = Binv @ torque_cmd
        
        B_mat = np.zeros((3, Idx["NU"]))
        B_mat[:,Idx["U"]["RW_TORQUE"]]  = self.G_rw_b.T
        mag_field = state[Idx["X"]["MAG_FIELD"]]
        Re2b = quatrotation(state[Idx["X"]["QUAT"]]).T
        bfMAG_FIELD = Re2b @ mag_field
        B_mat[:,Idx["U"]["MTB_TORQUE"]] = -crossproduct(bfMAG_FIELD)  @ self.G_mtb_b.T
        
        self.allocation_mat = np.zeros((Idx["NU"],3))
        self.allocation_mat[Idx["U"]["MTB_TORQUE"],:] = np.linalg.pinv(self.G_mtb_b.T)
                
        # np.linalg.pinv(B_mat)
        
        # Normalize columns of the allocation matrix
        # col_norms = np.linalg.norm(allocation_mat, axis=0)
        # allocation_mat = allocation_mat / col_norms
        
        actuator_cmd = self.allocation_mat @ torque_cmd
        return actuator_cmd
    
    def run(self, date, est_world_states, Idx):
        
        self.est_world_states = est_world_states
        # define slew profile
        ref_torque, ref_ctrl_states = self.define_att_profile(date, self.pointing_mode, self.pointing_target, 
                                                              self.tgt_ang_vel, est_world_states)
        # feedforward and feedback controller
        torque_cmd = self.get_torque(date, ref_torque, ref_ctrl_states, self.est_world_states, Idx)
        
        # actuator management function
        actuator_cmd = self.allocate_torque(self.est_world_states, torque_cmd, Idx)

        # convert to voltage      
        volt_cmd = np.zeros((Idx["NU"],))
        for i in range(len(self.mtb)):
            volt_cmd[Idx["U"]["MTB_TORQUE"]][i] = self.mtb[i].convert_dipole_moment_to_voltage(actuator_cmd[Idx["U"]["MTB_TORQUE"]][i])
        
        return volt_cmd.flatten()

        