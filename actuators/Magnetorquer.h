#ifndef C___magnetorquer_H
#define C___magnetorquer_H

#include "math/EigenWrapper.h"

double COPPER_RESISTIVITY = 1.724e-8;
class Magnetorquer {
    public:
        Magnetorquer(int N_MTBs, double maxVolt, double coilsPerLayer, double layers, double traceThickness,
                     double traceWidth, double gapWidth, double maxPower, double maxCurrentRating,
                     MatrixXd mtb_orientation);

        /**
        * @brief Computes Torque on the body frame from input current 
        * 
        * @param voltages : voltages for each magnetorquer [UNITS: A]
        * @param q : satellite attitude quaternion representing a rotation from Body to ECI frames
        * @param magnetic_field : current magnetic field vector in ECI
        * @return torque due to the single magnetorquer on the satellite [UNITS: Nm]
        */
        Vector3 getTorque(VectorXd voltages, Quaternion q, Vector3 magnetic_field);

    private:
        double num_MTBs; 
        double max_voltage;
        double N; // coils per layer
        double pcb_layers; // Number of layers
        double N_per_face; 
        double trace_thickness;
        double trace_width;
        double gap_width;
        double coil_width;
        double max_power;
        double max_current_rating;
        double pcb_side_max;
        double A_cross;
        double resistance;
        MatrixXd G_mtb_b;
};


#endif   // C___magnetorquer_H