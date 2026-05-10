
import numpy as np

VEH = {
    "mass_kg": 5000,
    "drag_coeff": 0.35,
    "frontal_area_m2": 3.0,
    "roll_resist": 0.012,
    "fc_max_kw": 150.0,
    "fc_eff_map": 0.35,
    "fc_heat_cap_kj_k": 80.0,
    "fc_ambient_coeff": 0.01,
    "aux_kw": 1.5,
    "hvac_cop_heat": 2.5,
    "hvac_cop_cool": 3.0,
    "cabin_heat_cap_kj_k": 15.0,
    "cabin_ua_w_k": 80.0,
    "setpoint_c": 21.0,
}

RHO_AIR = 1.2
G = 9.81
DT = 1.0

SEASONS = {
    "Winter (December)": {"anchorage_temp_c": -9.0, "juneau_temp_c": -3.0},
    "Summer (May)":      {"anchorage_temp_c":  8.0, "juneau_temp_c": 10.0},
}

def make_drive_cycle(seed=42):
    rng = np.random.default_rng(seed)
    v = np.zeros(2700)
    v_cur = 0.0
    for t in range(1, 2700):
        phase = (t // 120) % 4
        if phase == 0:   target = rng.uniform(8, 14)
        elif phase == 1: target = rng.uniform(0,  4)
        elif phase == 2: target = 0.0
        else:            target = rng.uniform(5, 10)
        step = np.clip(target - v_cur, -2.0, 2.0)
        v_cur = max(0, v_cur + step)
        v[t] = v_cur / 3.6
    return v

CYCLE = make_drive_cycle()

def simulate(ambient_c):
    T_fc = ambient_c
    T_cab = ambient_c
    fc_fuel_kj = 0.0
    hvac_kj = 0.0
    brake_kj = 0.0
    dist_m = 0.0
    for t in range(1, len(CYCLE)):
        v = CYCLE[t]
        dv = CYCLE[t] - CYCLE[t-1]
        v_avg = 0.5 * (CYCLE[t] + CYCLE[t-1])
        F_drag  = 0.5 * RHO_AIR * VEH["drag_coeff"] * VEH["frontal_area_m2"] * v**2
        F_roll  = VEH["roll_resist"] * VEH["mass_kg"] * G
        F_accel = VEH["mass_kg"] * dv / DT
        F_total = F_drag + F_roll + F_accel
        P_trac_w = F_total * v
        if P_trac_w >= 0:
            warm_factor = np.clip((T_fc - ambient_c) / 60.0, 0, 1)
            eff = VEH["fc_eff_map"] * (0.7 + 0.3 * warm_factor)
            P_fc_kw = (P_trac_w / 1000) / max(eff, 0.15)
            heat_gen_kw = P_fc_kw - P_trac_w / 1000
            fc_fuel_kj += P_fc_kw * DT
        else:
            brake_kj += -P_trac_w / 1000 * 0.95 * DT
            heat_gen_kw = 0.0
        dT_fc = (heat_gen_kw - VEH["fc_ambient_coeff"] * (T_fc - ambient_c)) / VEH["fc_heat_cap_kj_k"] * DT
        T_fc += dT_fc
        Q_loss_w = VEH["cabin_ua_w_k"] * (T_cab - ambient_c)
        err = VEH["setpoint_c"] - T_cab
        if err > 0:
            Q_hvac_kw = min(abs(err) * 0.5, 5.0)
            P_hvac_kw = Q_hvac_kw / VEH["hvac_cop_heat"]
        elif err < -1:
            Q_hvac_kw = -min(abs(err) * 0.5, 5.0)
            P_hvac_kw = abs(Q_hvac_kw) / VEH["hvac_cop_cool"]
        else:
            Q_hvac_kw = 0.0
            P_hvac_kw = 0.0
        dT_cab = (Q_hvac_kw * 1000 - Q_loss_w) / (VEH["cabin_heat_cap_kj_k"] * 1000) * DT
        T_cab += dT_cab
        hvac_kj += P_hvac_kw * DT
        dist_m += v_avg * DT
    dist_km = dist_m / 1000
    total_kj = fc_fuel_kj + hvac_kj + VEH["aux_kw"] * len(CYCLE)
    return {
        "dist_km":     round(dist_km, 2),
        "fc_fuel_kwh": round(fc_fuel_kj / 3600, 3),
        "hvac_kwh":    round(hvac_kj    / 3600, 3),
        "aux_kwh":     round(VEH["aux_kw"] * len(CYCLE) / 3600, 3),
        "regen_kwh":   round(brake_kj   / 3600, 3),
        "total_kwh":   round(total_kj   / 3600, 3),
        "kwh_per_km":  round(total_kj / 3600 / max(dist_km, 0.001), 4),
    }

print("=" * 65)
print("  ALASKA TRANSIT ENERGY — FASTSim Thermal Model Results")
print("=" * 65)
results = {}
for season, info in SEASONS.items():
    results[season] = {}
    print(f"\n  ── {season} ──")
    for city, key in [("Anchorage (People Mover)", "anchorage_temp_c"),
                      ("Juneau (Capital Transit)",  "juneau_temp_c")]:
        T = info[key]
        r = simulate(T)
        results[season][city] = r
        print(f"    {city}  |  Ambient: {T:+.0f}C")
        print(f"      Traction:  {r['fc_fuel_kwh']} kWh")
        print(f"      HVAC:      {r['hvac_kwh']} kWh")
        print(f"      Aux:       {r['aux_kwh']} kWh")
        print(f"      Regen:     {r['regen_kwh']} kWh")
        print(f"      TOTAL:     {r['total_kwh']} kWh")
        print(f"      Eff:       {r['kwh_per_km']} kWh/km")

print("\n  ── Winter vs Summer Delta ──")
for city in ["Anchorage (People Mover)", "Juneau (Capital Transit)"]:
    w = results["Winter (December)"][city]["total_kwh"]
    s = results["Summer (May)"][city]["total_kwh"]
    print(f"    {city}: Winter uses {(w-s)/s*100:+.1f}% more energy")
