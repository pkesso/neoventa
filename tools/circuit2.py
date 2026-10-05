"""Venta Overdrive v2: SMD build for JLCPCB assembly, 125B enclosure.
Single source of truth for schematic, SPICE deck, PCB and BOM.
kind, ref, value, pins{pin: net}, footprint, side, lcsc, note
side: 'B' = SMD on bottom (assembled by JLCPCB), 'F' = through-hole on top (hand-soldered)."""

R0805 = "Resistor_SMD:R_0805_2012Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
POT1 = "Venta:Pot_Alpha_16mm_RA_Single"
POT2 = "Venta:Pot_Alpha_16mm_RA_Dual"
PAD = "Venta:WirePad"

COMPONENTS = [
    # power
    ("DS", "D3", "SS14", {"A": "+9V_IN", "K": "VCC"}, "Diode_SMD:D_SMA", "B", "C2480", "reverse-polarity protection (was 1N5817)"),
    ("C", "C1", "22u", {"1": "VCC", "2": "GND"}, C1206, "B", "C12891", "bulk, 25V X5R (was 47u electrolytic)"),
    ("R", "R1", "10k", {"1": "VCC", "2": "VB"}, R0805, "B", "C17414", ""),
    ("R", "R2", "10k", {"1": "VB", "2": "GND"}, R0805, "B", "C17414", ""),
    ("C", "C2", "10u", {"1": "VB", "2": "GND"}, C0805, "B", "C15850", "25V X5R"),
    ("C", "C10", "100n", {"1": "VCC", "2": "GND"}, C0805, "B", "C49678", "U1 decoupling (new)"),
    ("C", "C11", "100n", {"1": "VCC", "2": "GND"}, C0805, "B", "C49678", "U2 decoupling (new)"),
    ("C", "C12", "100n", {"1": "VCC", "2": "GND"}, C0805, "B", "C49678", "U3 decoupling (new)"),
    # input buffer
    ("R", "R3", "1M", {"1": "IN", "2": "GND"}, R0805, "B", "C17514", "input pulldown (was 1.5M)"),
    ("C", "C3", "22n", {"1": "IN", "2": "BUF_IN"}, C0805, "B", "C1729", ""),
    ("R", "R4", "220k", {"1": "BUF_IN", "2": "VREF"}, R0805, "B", "C17556", ""),
    ("C", "C4", "220n", {"1": "BUF_OUT", "2": "DRIVE_HI"}, C0805, "B", "C5378", ""),
    # gain + clipper
    ("R", "R5", "680k", {"1": "GAIN_OUT", "2": "GAIN_FB"}, R0805, "B", "C17797", ""),
    ("R", "R6", "4.7k", {"1": "GAIN_FB", "2": "GAIN_RC"}, R0805, "B", "C17673", ""),
    ("C", "C5", "680n", {"1": "GAIN_RC", "2": "VREF"}, C0805, "B", "C107133", "50V X7R"),
    ("R", "R7", "1k", {"1": "GAIN_OUT", "2": "CLIP"}, R0805, "B", "C17513", ""),
    ("D", "D1", "1N4148W", {"A": "CLIP", "K": "VREF"}, "Diode_SMD:D_SOD-123", "B", "C81598", ""),
    ("D", "D2", "1N4148W", {"A": "VREF", "K": "CLIP"}, "Diode_SMD:D_SOD-123", "B", "C81598", ""),
    # state-variable filter
    ("R", "R8", "15k", {"1": "CLIP", "2": "SUM"}, R0805, "B", "C17475", ""),
    ("R", "R9", "33k", {"1": "SUM", "2": "HP"}, R0805, "B", "C17633", ""),
    ("R", "R10", "33k", {"1": "SUM", "2": "LP"}, R0805, "B", "C17633", ""),
    ("R", "R11", "3k", {"1": "RES", "2": "VREF"}, R0805, "B", "C17661", ""),
    ("R", "R12", "15k", {"1": "HP", "2": "EQ_A"}, R0805, "B", "C17475", ""),
    ("C", "C6", "1.5n", {"1": "BP", "2": "INT1_N"}, C0603, "B", "C107039", "C0G/NP0"),
    ("R", "R13", "15k", {"1": "EQ_B", "2": "INT2_N"}, R0805, "B", "C17475", ""),
    ("C", "C7", "1.5n", {"1": "LP", "2": "INT2_N"}, C0603, "B", "C107039", "C0G/NP0"),
    # output
    ("C", "C8", "220n", {"1": "LP", "2": "LP_AC"}, C0805, "B", "C5378", ""),
    ("R", "R14", "3.3k", {"1": "LP_AC", "2": "VOL_HI"}, R0805, "B", "C26010", ""),
    ("C", "C9", "220n", {"1": "VOL_W", "2": "OUT_DC"}, C0805, "B", "C5378", ""),
    ("R", "R15", "100k", {"1": "OUT_DC", "2": "GND"}, R0805, "B", "C149504", ""),
    ("R", "R16", "1k", {"1": "OUT_DC", "2": "OUT"}, R0805, "B", "C17513", ""),
    # op-amps
    ("OPAMP2", "U1", "JRC4558D", {"1": "GAIN_OUT", "2": "GAIN_FB", "3": "DRIVE_W", "4": "GND",
                                  "5": "BUF_IN", "6": "BUF_OUT", "7": "BUF_OUT", "8": "VCC"},
     "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "B", "C443686", "U1A gain, U1B input buffer"),
    ("OPAMP2", "U2", "JRC4558D", {"1": "HP", "2": "SUM", "3": "RES", "4": "GND",
                                  "5": "VREF", "6": "INT1_N", "7": "BP", "8": "VCC"},
     "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "B", "C443686", "U2A summer, U2B integrator 1"),
    ("OPAMP2", "U3", "JRC4558D", {"1": "VREF", "2": "VREF", "3": "VB", "4": "GND",
                                  "5": "VREF", "6": "INT2_N", "7": "LP", "8": "VCC"},
     "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "B", "C443686", "U3A Vref buffer, U3B integrator 2"),
    # pots (hand-soldered, Alpha 16 mm right-angle PCB mount)
    ("POT", "RV1", "B50k Drive", {"1": "VREF", "2": "DRIVE_W", "3": "DRIVE_HI"}, POT1, "F", "", ""),
    ("POT", "RV2", "B50k Resonance", {"1": "RES", "2": "RES", "3": "BP"}, POT1, "F", "", ""),
    ("POT2", "RV3", "B50k dual Eq", {"1": "INT1_N", "2": "INT1_N", "3": "EQ_A", "4": "EQ_B", "5": "EQ_B", "6": "BP"}, POT2, "F", "", ""),
    ("POT", "RV4", "B50k Volume", {"1": "GND", "2": "VOL_W", "3": "VOL_HI"}, POT1, "F", "", ""),
    # wire pads
    ("PAD", "J1", "IN", {"1": "IN"}, PAD, "F", "", "from 3PDT (effect in)"),
    ("PAD", "J2", "OUT", {"1": "OUT"}, PAD, "F", "", "to 3PDT (effect out)"),
    ("PAD", "J3", "9V", {"1": "+9V_IN"}, PAD, "F", "", "from DC jack (+9 V)"),
    ("PAD", "J4", "GND", {"1": "GND"}, PAD, "F", "", "DC jack ground"),
    ("PAD", "J5", "GND", {"1": "GND"}, PAD, "F", "", "jacks / 3PDT ground"),
    # external status LED with its own resistor: anode to J6, cathode to a 3PDT lug, that pole's common to J7
    ("PAD", "J6", "LED+", {"1": "VCC"}, PAD, "F", "", "to the external LED anode (LED has its own resistor)"),
    ("PAD", "J7", "GND", {"1": "GND"}, PAD, "F", "", "to the common of the 3PDT pole that switches the LED"),
]

POT_POS = {"RV1": 0.5, "RV2": 0.5, "RV3": 0.5, "RV4": 0.5}


def spice_deck(vin_amp=0.1, freq=440, pos=None, analysis=".tran 5u 60m 50m"):
    pos = dict(POT_POS, **(pos or {}))
    n = lambda x: "0" if x == "GND" else x.replace("+", "P")
    L = ["* Venta Overdrive v2", ".include venta.lib",
         f"V1 IN 0 DC 0 AC 1 SIN(0 {vin_amp} {freq})", "V2 P9V_IN 0 DC 9", "RLOAD OUT 0 1Meg"]
    for kind, ref, val, pins, fp, side, lcsc, note in COMPONENTS:
        if kind in ("R", "C"):
            L.append(f"{ref} {n(pins['1'])} {n(pins['2'])} {val.replace('M', 'Meg')}")
        elif kind in ("D", "DS", "LED"):
            m = {"D": "D1N4148", "DS": "D1N5817", "LED": "DLED"}[kind]
            L.append(f"{ref} {n(pins['A'])} {n(pins['K'])} {m}")
        elif kind == "OPAMP2":
            L.append(f"X{ref} " + " ".join(n(pins[str(i)]) for i in range(1, 9)) + " DUAL_OPAMP")
        elif kind == "POT":
            L.append(f"X{ref} " + " ".join(n(pins[str(i)]) for i in range(1, 4)) + f" POT R=50k POS={pos[ref]}")
        elif kind == "POT2":
            L.append(f"X{ref} " + " ".join(n(pins[str(i)]) for i in range(1, 7)) + f" POT_DUAL R=50k POS={pos[ref]}")
    L += [analysis, ".end"]
    return "\n".join(L) + "\n"
