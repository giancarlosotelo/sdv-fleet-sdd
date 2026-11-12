"""VSS signal paths used by the van. Standard ones are VSS 4.0; Vehicle.Fleet.* are in vss/overlay.vspec."""

LAT = "Vehicle.CurrentLocation.Latitude"
LON = "Vehicle.CurrentLocation.Longitude"
SPEED = "Vehicle.Speed"  # km/h
ACCEL = "Vehicle.Acceleration.Longitudinal"  # m/s², negative is braking
TRACTION = "Vehicle.ADAS.TCS.IsEngaged"
SOC = "Vehicle.Powertrain.TractionBattery.StateOfCharge.Current"  # %
COOLANT = "Vehicle.Powertrain.ElectricMotor.CoolantTemperature"  # °C
ODOMETER = "Vehicle.TraveledDistance"  # km

TRIP = "Vehicle.Fleet.TripNumber"
SIM_TIME = "Vehicle.Fleet.SimTime"  # s since simulation start
HAZARD_TYPE = "Vehicle.Fleet.Hazard.Type"  # "none" or a rules.HazardType value
HAZARD_SEVERITY = "Vehicle.Fleet.Hazard.Severity"  # 0 none .. 3 critical
HAZARD_T0 = "Vehicle.Fleet.Hazard.T0"  # UTC epoch ms when the current hazard was detected

STANDARD = (LAT, LON, SPEED, ACCEL, TRACTION, SOC, COOLANT, ODOMETER)
CUSTOM = (TRIP, SIM_TIME, HAZARD_TYPE, HAZARD_SEVERITY, HAZARD_T0)
ALL = STANDARD + CUSTOM
RULE_INPUTS = (SPEED, ACCEL, TRACTION, SOC, COOLANT)
