import numpy as np
from world.math.quaternions import crossproduct, quatrotation


COPPER_RESISTIVITY = 1.724 * 10**-8


# This is a single torquer
class Magnetorquer:
    def __init__(
        self,
        config,
        IdMtb,
        max_voltage=5,
        coils_per_layer=32.0,
        layers=2.0,
        trace_width=0.0007317,  # m
        gap_width=8.999 * 10**-5,  # m
        trace_thickness=3.556 * 10**-5,  # 1oz copper - 35um = 1.4 mils
        max_current_rating=1,  # A
        max_power=0.25,  # W
    ) -> None:
        self.max_voltage = config["max_voltage"][IdMtb]
        self.N = config["coils_per_layer"][IdMtb]
        self.pcb_layers = config["layers"][IdMtb]
        self.N_per_face = self.N * self.pcb_layers
        self.trace_thickness = config["trace_thickness"][IdMtb] 
        self.trace_width = config["trace_width"][IdMtb] 
        self.gap_width = config["gap_width"][IdMtb] 
        self.coil_width =  self.trace_width + self.gap_width
        self.max_power = config["max_power"][IdMtb]
        self.max_current_rating = config["max_current_rating"][IdMtb] 
        # I_max = min Imax, Vmax / R 
        # D_max = N * I_max * A * G  

        self.pcb_side_max = 0.1
        self.A_cross = (self.pcb_side_max - self.N * self.coil_width) ** 2
        self.R = self.compute_coil_resistance()

        self.max_current = np.min([self.max_current_rating, np.sqrt(self.max_power / self.R) ])
        self.max_current = np.min([self.max_current, self.max_voltage / self.R ])
        self.max_voltage = self.R * self.max_current
        self.max_power   = self.R * self.max_current ** 2
        self.max_dipole_moment = self.N_per_face * self.max_current * self.A_cross  # A*m^2
        self.G_mtb_b = np.array(config["mtb_orientation"][(3*IdMtb):(3*(IdMtb+1))]).T
        self.dipole_moment = np.zeros(3,)
        self.current = 0.0
        self.voltage = 0.0
        self.power   = 0.0

    def get_dipole_moment(self):
        return self.dipole_moment


    def get_torque(self, MAG_FIELD):
        """
        Update voltage or current before getting the torque.
        """
        # TODO: Get moment and field in whatever frame the sim wants torque
        return crossproduct(self.dipole_moment) @ MAG_FIELD


    def get_power(self):
        return  self.R * self.current ** 2

    def set_voltage(
        self,
        voltage: float,
    ) -> None:
        if np.abs(voltage) > self.max_voltage:
            raise ValueError("Voltage exceeds maximum voltage rating.")
        # Current driver is PWM
        self.voltage = voltage
        self.current = voltage / self.R
        self.power   = self.R * self.current ** 2
        if abs(self.current) > self.max_current:
            raise ValueError(
                f"Current exceeds maximum power limit of {self.max_power} W."
            )
        self.dipole_moment = self.convert_current_to_dipole_moment(self.current)

    def set_current(
        self,
        current: float,
    ) -> None:
        if np.abs(current) > self.max_current:
            raise ValueError(
                f"Current exceeds maximum power limit of {self.max_power} W."
            )
        self.dipole_moment = self.convert_current_to_dipole_moment(current)

    def set_dipole_moment(
        self,
        dipole_moment: float,
    ) -> None:
        if np.abs(dipole_moment) > self.max_dipole_moment:
            raise ValueError(
                f"Dipole Moment exceeds maximum dipole moment limit of {self.max_dipole_moment} Cm."
            )
        self.dipole_moment = dipole_moment * self.G_mtb_b

    def get_dipole_moment_over_current(self) -> float:
        return self.N_per_face * self.A_cross

    def convert_current_to_dipole_moment(
        self,
        current: float,
    ) -> np.ndarray:
        #TODO: confirm that G_mtb_b is unit vector
        current = np.clip(a=current, a_min=-self.max_current, a_max=self.max_current)
        return self.N_per_face * current * self.A_cross * self.G_mtb_b

    def convert_dipole_moment_to_voltage(
        self,
        dipole_moment: np.ndarray,
    ) -> float:
        self.dipole_moment = np.clip(a=dipole_moment, a_min=-self.max_dipole_moment, a_max=self.max_dipole_moment)
        I = self.convert_dipole_moment_to_current(self.dipole_moment)
        self.current = np.clip(a=I, a_min=-self.max_current, a_max=self.max_current)
        # clip voltage to max voltage
        self.voltage = np.clip(a=self.current * self.R, a_min=-self.max_voltage, a_max=self.max_voltage)
        self.power   = self.R * self.current ** 2
        return self.voltage

    def convert_voltage_to_dipole_moment(
        self,
        voltage: float,
    ) -> np.ndarray:
        self.voltage = voltage
        I = voltage / self.R
        # clip current to max current
        self.current = np.clip(a=I, a_min=-self.max_current, a_max=self.max_current)
        self.dipole_moment = self.convert_current_to_dipole_moment(self.current)
        self.power   = self.R * self.current ** 2
        return self.dipole_moment

    def convert_dipole_moment_to_current(
        self,
        dipole_moment: np.ndarray,
    ) -> float:
        dipole_moment = np.clip(a=dipole_moment, a_min=-self.max_dipole_moment, a_max=self.max_dipole_moment)
        return dipole_moment / self.N_per_face / self.A_cross

    def compute_coil_resistance(self):
        coil_length = 4 * (self.pcb_side_max - self.N*self.coil_width) \
                        * self.N * self.pcb_layers
        R =  COPPER_RESISTIVITY * coil_length \
            / (self.trace_width * self.trace_thickness)
        return R