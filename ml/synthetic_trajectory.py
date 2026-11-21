from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass
class SyntheticTrajectory:
    trajectory_id: int
    split: str
    scenario: str
    timestamps: np.ndarray
    position: np.ndarray
    velocity: np.ndarray
    speed: np.ndarray
    heading_sin: np.ndarray
    heading_cos: np.ndarray
    position_valid: np.ndarray
    ground_truth_position: np.ndarray | None = None
    ground_truth_velocity: np.ndarray | None = None
    segment_ids: np.ndarray | None = None
    seed: int = 0


@dataclass(frozen=True)
class SensorNoise:
    """Illustrative observation noise; these defaults are not calibrated to hardware."""
    position_noise_std: float = 0.15
    velocity_noise_std: float = 0.10
    heading_noise_std_deg: float = 2.0
    position_drift_std: float = 0.02  # m / sqrt(s), random walk
    timing_jitter_std: float = 0.01  # s, bounded to preserve observation order
    dropout_probability: float = 0.01
    outage_probability: float = 0.5
    outage_duration_s: float = 0.7
    reset_probability: float = 0.5
    reset_jump_std: float = 0.5  # m; estimator correction, not physical motion

    def __post_init__(self):
        for name, value in asdict(self).items():
            if not np.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative.")
            if name.endswith("probability") and value > 1:
                raise ValueError(f"{name} must be in [0, 1].")


SCENARIOS = [
    "accelerate_decelerate",
    "turn_90",
    "smooth_turn",
    "circle",
    "climb_and_cruise",
    "figure_eight",
    "stop_turn_stop",
    "mixed_3d",
]


def smoothstep(u: np.ndarray) -> np.ndarray:
    """Cubic smoothstep: 0 -> 0, 1 -> 1 with zero endpoint slope."""
    u = np.clip(u, 0.0, 1.0)
    return 3.0 * u**2 - 2.0 * u**3


def smooth_segment(
    t: np.ndarray,
    start: float,
    duration: float,
    p0: np.ndarray,
    p1: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Smoothly move from p0 to p1 over a fixed time interval.

    Returns position and velocity.
    """
    u = (t - start) / duration
    s = smoothstep(u)

    ds_du = 6.0 * u * (1.0 - u)
    velocity = ds_du[:, None] * (p1 - p0)[None, :] / duration
    position = p0[None, :] + s[:, None] * (p1 - p0)[None, :]

    return position, velocity


def scenario_accelerate_decelerate(
    t: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Straight flight with smooth acceleration, cruise and deceleration.

    The speed profile uses a smoothstep transition:
        v(u) = speed * (3u^2 - 2u^3)

    during acceleration, and its time-reversed form during
    deceleration. Position is obtained from the analytical
    integral of the velocity profile, so position and velocity
    remain consistent.
    """
    speed = rng.uniform(3.0, 6.0)
    direction = rng.uniform(0.0, 2.0 * np.pi)

    unit = np.array(
        [
            np.cos(direction),
            np.sin(direction),
            0.0,
        ]
    )

    start = np.array(
        [0.0, 0.0, rng.uniform(10.0, 30.0)]
    )

    accel_time = 8.0
    cruise_time = 30.0
    decel_time = 8.0
    total = accel_time + cruise_time + decel_time

    position = np.zeros((len(t), 3))
    velocity = np.zeros((len(t), 3))

    for i, ti in enumerate(t):

        if ti < accel_time:
            u = ti / accel_time

            # Smoothstep velocity:
            # v(u) = speed * (3u^2 - 2u^3)
            v_factor = 3.0 * u**2 - 2.0 * u**3

            # Integral of smoothstep from 0 to u:
            # u^3 - 0.5u^4
            distance = (
                speed
                * accel_time
                * (u**3 - 0.5 * u**4)
            )

            position[i] = start + unit * distance
            velocity[i] = unit * speed * v_factor

        elif ti < accel_time + cruise_time:
            tau = ti - accel_time

            accel_distance = 0.5 * speed * accel_time

            position[i] = (
                start
                + unit * (accel_distance + speed * tau)
            )
            velocity[i] = unit * speed

        elif ti < total:
            tau = ti - accel_time - cruise_time
            u = tau / decel_time

            accel_distance = 0.5 * speed * accel_time
            cruise_distance = speed * cruise_time

            # Reverse smoothstep velocity:
            # v(u) = speed * (1 - 3u^2 + 2u^3)
            v_factor = 1.0 - 3.0 * u**2 + 2.0 * u**3

            # Integral of the reverse smoothstep:
            # u - u^3 + 0.5u^4
            distance = (
                speed
                * decel_time
                * (u - u**3 + 0.5 * u**4)
            )

            position[i] = (
                start
                + unit * (
                    accel_distance
                    + cruise_distance
                    + distance
                )
            )
            velocity[i] = unit * speed * v_factor

        else:
            # Remain stationary after the maneuver.
            final_distance = (
                speed * (
                    cruise_time
                    + 0.5 * accel_time
                    + 0.5 * decel_time
                )
            )

            position[i] = start + unit * final_distance
            velocity[i] = np.zeros(3)

    return position, velocity

def scenario_turn_90(
    t: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Straight flight followed by a smooth 90-degree turn.
    """
    speed = rng.uniform(3.0, 5.0)
    turn_start = 20.0
    turn_duration = 8.0

    heading0 = rng.uniform(0.0, 2.0 * np.pi)

    position = np.zeros((len(t), 3))
    velocity = np.zeros((len(t), 3))

    p0 = np.array(
        [
            rng.uniform(-20.0, 20.0),
            rng.uniform(-20.0, 20.0),
            rng.uniform(15.0, 30.0),
        ]
    )

    for i, ti in enumerate(t):

        if ti < turn_start:
            heading = heading0
            displacement = speed * ti

        elif ti < turn_start + turn_duration:
            tau = ti - turn_start
            u = tau / turn_duration
            turn = 0.5 * np.pi * smoothstep(np.array([u]))[0]
            heading = heading0 + turn

            displacement = speed * turn_start

            # Integrate the turning velocity numerically from
            # the beginning of the turn to current time.
            local_times = np.linspace(0.0, tau, 50)

            if tau > 0:
                local_u = local_times / turn_duration
                local_turn = 0.5 * np.pi * smoothstep(local_u)
                dx = np.trapezoid(
                    speed * np.cos(heading0 + local_turn),
                    local_times,
                )
                dy = np.trapezoid(
                    speed * np.sin(heading0 + local_turn),
                    local_times,
                )
                displacement_vector = np.array([dx, dy, 0.0])
            else:
                displacement_vector = np.zeros(3)

            position[i] = (
                p0
                + np.array(
                    [
                        speed * turn_start * np.cos(heading0),
                        speed * turn_start * np.sin(heading0),
                        0.0,
                    ]
                )
                + displacement_vector
            )

            velocity[i] = np.array(
                [
                    speed * np.cos(heading),
                    speed * np.sin(heading),
                    0.0,
                ]
            )
            continue

        else:
            heading = heading0 + 0.5 * np.pi

            turn_times = np.linspace(0.0, turn_duration, 100)
            turn_u = turn_times / turn_duration
            turn_heading = heading0 + 0.5 * np.pi * smoothstep(turn_u)

            turn_dx = np.trapezoid(
                speed * np.cos(turn_heading),
                turn_times,
            )
            turn_dy = np.trapezoid(
                speed * np.sin(turn_heading),
                turn_times,
            )

            displacement_vector = np.array(
                [turn_dx, turn_dy, 0.0]
            )

            position[i] = (
                p0
                + np.array(
                    [
                        speed * turn_start * np.cos(heading0),
                        speed * turn_start * np.sin(heading0),
                        0.0,
                    ]
                )
                + displacement_vector
                + np.array(
                    [
                        speed * (ti - turn_start - turn_duration)
                        * np.cos(heading),
                        speed * (ti - turn_start - turn_duration)
                        * np.sin(heading),
                        0.0,
                    ]
                )
            )

            velocity[i] = np.array(
                [
                    speed * np.cos(heading),
                    speed * np.sin(heading),
                    0.0,
                ]
            )
            continue

        position[i] = p0 + np.array(
            [
                displacement * np.cos(heading),
                displacement * np.sin(heading),
                0.0,
            ]
        )

        velocity[i] = np.array(
            [
                speed * np.cos(heading),
                speed * np.sin(heading),
                0.0,
            ]
        )

    return position, velocity


def scenario_smooth_turn(
    t: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Smooth sinusoidal heading changes.
    """
    speed = rng.uniform(2.0, 5.0)
    omega = rng.uniform(0.08, 0.16)
    amplitude = rng.uniform(0.5, 1.2)

    heading0 = rng.uniform(0.0, 2.0 * np.pi)

    heading = heading0 + amplitude * np.sin(omega * t)

    velocity = np.column_stack(
        [
            speed * np.cos(heading),
            speed * np.sin(heading),
            np.zeros_like(t),
        ]
    )

    position = np.zeros_like(velocity)
    position[0] = np.array(
        [
            rng.uniform(-30.0, 30.0),
            rng.uniform(-30.0, 30.0),
            rng.uniform(15.0, 30.0),
        ]
    )

    position[1:] = position[0] + np.cumsum(
        0.5 * (velocity[1:] + velocity[:-1])
        * np.diff(t)[:, None],
        axis=0,
    )

    return position, velocity


def scenario_circle(
    t: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Constant-speed circular trajectory.
    """
    radius = rng.uniform(15.0, 40.0)
    angular_speed = rng.uniform(0.08, 0.18)

    phase = rng.uniform(0.0, 2.0 * np.pi)

    center = np.array(
        [
            rng.uniform(-30.0, 30.0),
            rng.uniform(-30.0, 30.0),
            rng.uniform(15.0, 30.0),
        ]
    )

    angle = phase + angular_speed * t

    position = np.column_stack(
        [
            center[0] + radius * np.cos(angle),
            center[1] + radius * np.sin(angle),
            np.full_like(t, center[2]),
        ]
    )

    velocity = np.column_stack(
        [
            -radius * angular_speed * np.sin(angle),
            radius * angular_speed * np.cos(angle),
            np.zeros_like(t),
        ]
    )

    return position, velocity


def scenario_climb_and_cruise(
    t: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Horizontal flight combined with a smooth climb and descent.
    """
    speed = rng.uniform(2.5, 5.0)
    heading = rng.uniform(0.0, 2.0 * np.pi)

    vx = speed * np.cos(heading)
    vy = speed * np.sin(heading)

    x = vx * t
    y = vy * t

    altitude = 15.0 + 12.0 * np.sin(
        2.0 * np.pi * t / t[-1]
    )

    vz = (
        12.0
        * 2.0
        * np.pi
        / t[-1]
        * np.cos(2.0 * np.pi * t / t[-1])
    )

    position = np.column_stack([x, y, altitude])
    velocity = np.column_stack(
        [
            np.full_like(t, vx),
            np.full_like(t, vy),
            vz,
        ]
    )

    return position, velocity


def scenario_figure_eight(
    t: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Horizontal figure-eight trajectory.
    """
    amplitude = rng.uniform(20.0, 40.0)
    omega = rng.uniform(0.07, 0.12)

    phase = rng.uniform(0.0, 2.0 * np.pi)

    angle = omega * t + phase

    x = amplitude * np.sin(angle)
    y = amplitude * np.sin(angle) * np.cos(angle)

    vx = amplitude * omega * np.cos(angle)
    vy = amplitude * omega * np.cos(2.0 * angle)

    z0 = rng.uniform(15.0, 30.0)

    position = np.column_stack(
        [
            x,
            y,
            np.full_like(t, z0),
        ]
    )

    velocity = np.column_stack(
        [
            vx,
            vy,
            np.zeros_like(t),
        ]
    )

    return position, velocity


def scenario_stop_turn_stop(
    t: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Hover -> accelerate -> cruise -> smooth turn ->
    cruise -> decelerate -> hover.
    """
    p0 = np.array(
        [
            rng.uniform(-20.0, 20.0),
            rng.uniform(-20.0, 20.0),
            rng.uniform(15.0, 30.0),
        ]
    )

    speed = rng.uniform(3.0, 5.0)

    heading1 = rng.uniform(0.0, 2.0 * np.pi)

    # Sample the turn angle once per trajectory.
    # It must not change at every timestep.
    turn_angle = rng.uniform(
        0.5 * np.pi,
        1.5 * np.pi,
    )

    heading2 = heading1 + turn_angle

    velocity = np.zeros((len(t), 3))
    position = np.zeros((len(t), 3))

    position[0] = p0

    for i, ti in enumerate(t):

        # ----------------------------------------------------------
        # Hover
        # ----------------------------------------------------------
        if ti < 8.0:

            u = ti / 8.0
            s = smoothstep(np.array([u]))[0]

            v = speed * s
            heading = heading1

        # ----------------------------------------------------------
        # Cruise before turn
        # ----------------------------------------------------------
        elif ti < 25.0:

            v = speed
            heading = heading1

        # ----------------------------------------------------------
        # Smooth turn
        # ----------------------------------------------------------
        elif ti < 33.0:

            u = (ti - 25.0) / 8.0

            turn_fraction = smoothstep(
                np.array([u])
            )[0]

            heading = heading1 + turn_angle * turn_fraction
            v = speed

        # ----------------------------------------------------------
        # Cruise after turn
        # ----------------------------------------------------------
        elif ti < 50.0:

            v = speed
            heading = heading2

        # ----------------------------------------------------------
        # Smooth deceleration
        # ----------------------------------------------------------
        elif ti < 58.0:

            u = (ti - 50.0) / 8.0

            v = speed * (
                1.0
                - smoothstep(np.array([u]))[0]
            )

            heading = heading2

        # ----------------------------------------------------------
        # Final hover
        # ----------------------------------------------------------
        else:

            v = 0.0
            heading = heading2

        velocity[i] = np.array(
            [
                v * np.cos(heading),
                v * np.sin(heading),
                0.0,
            ]
        )

        if i > 0:

            position[i] = (
                position[i - 1]
                + 0.5
                * (
                    velocity[i - 1]
                    + velocity[i]
                )
                * (t[i] - t[i - 1])
            )

    return position, velocity


def scenario_mixed_3d(
    t: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Deliberately difficult smooth 3D trajectory.
    """
    base_speed = rng.uniform(2.0, 4.0)

    omega1 = rng.uniform(0.08, 0.14)
    omega2 = rng.uniform(0.05, 0.10)

    heading = (
        rng.uniform(0.0, 2.0 * np.pi)
        + 0.9 * np.sin(omega1 * t)
        + 0.5 * np.sin(omega2 * t)
    )

    speed = (
        base_speed
        + 1.5 * np.sin(0.06 * t)
        + 0.8 * np.sin(0.13 * t)
    )

    speed = np.maximum(speed, 0.2)

    vx = speed * np.cos(heading)
    vy = speed * np.sin(heading)

    vz = (
        0.8 * np.sin(0.11 * t)
        + 0.5 * np.sin(0.23 * t)
    )

    velocity = np.column_stack([vx, vy, vz])

    position = np.zeros_like(velocity)

    position[0] = np.array(
        [
            rng.uniform(-20.0, 20.0),
            rng.uniform(-20.0, 20.0),
            rng.uniform(15.0, 30.0),
        ]
    )

    position[1:] = position[0] + np.cumsum(
        0.5 * (velocity[1:] + velocity[:-1])
        * np.diff(t)[:, None],
        axis=0,
    )

    return position, velocity


SCENARIO_FUNCTIONS = {
    "accelerate_decelerate": scenario_accelerate_decelerate,
    "turn_90": scenario_turn_90,
    "smooth_turn": scenario_smooth_turn,
    "circle": scenario_circle,
    "climb_and_cruise": scenario_climb_and_cruise,
    "figure_eight": scenario_figure_eight,
    "stop_turn_stop": scenario_stop_turn_stop,
    "mixed_3d": scenario_mixed_3d,
}


def add_measurement_noise(
    position: np.ndarray,
    rng: np.random.Generator,
    position_noise_std: float = 0.02,
) -> np.ndarray:
    """
    Add small measurement noise to position.

    Ground-truth velocity remains available separately.
    """
    noise = rng.normal(
        0.0,
        position_noise_std,
        size=position.shape,
    )

    return position + noise


def build_trajectory(
    trajectory_id: int, split: str, scenario: str, duration_s: float,
    interval_s: float, seed: int, noisy: bool = True, noise: SensorNoise | None = None,
) -> SyntheticTrajectory:
    if not np.isfinite(interval_s) or interval_s <= 0 or not np.isfinite(duration_s) or duration_s <= interval_s:
        raise ValueError("Duration and interval must be finite, with duration greater than interval.")
    if split not in {"train", "validation", "test"} or scenario not in SCENARIOS:
        raise ValueError("Unknown split or scenario.")
    noise = noise or SensorNoise()
    # Separate motion and observation RNG streams so changing sensor noise
    # leaves the underlying flight parameters fixed for paired experiments.
    motion_rng = np.random.default_rng(seed)
    sensor_rng = np.random.default_rng(np.random.SeedSequence([seed, 1]))
    timestamps = np.arange(0.0, duration_s + interval_s * 0.5, interval_s)
    if noisy and noise.timing_jitter_std:
        timestamps[1:-1] += np.clip(
            sensor_rng.normal(0, noise.timing_jitter_std, len(timestamps) - 2),
            -0.4 * interval_s, 0.4 * interval_s,
        )
    position, velocity = SCENARIO_FUNCTIONS[scenario](timestamps, motion_rng)
    measured_position, measured_velocity = position.copy(), velocity.copy()
    valid = np.ones(len(timestamps), dtype=bool)
    segments = np.zeros(len(timestamps), dtype=int)
    if noisy:
        dt = np.diff(timestamps, prepend=timestamps[0])
        drift = np.cumsum(sensor_rng.normal(size=position.shape)
                          * np.sqrt(dt[:, None]) * noise.position_drift_std, axis=0)
        measured_position += drift + sensor_rng.normal(0, noise.position_noise_std, position.shape)
        measured_velocity += sensor_rng.normal(0, noise.velocity_noise_std, velocity.shape)
        if sensor_rng.random() < noise.reset_probability:
            reset = int(sensor_rng.integers(max(1, len(timestamps) // 3),
                                            max(2, 2 * len(timestamps) // 3)))
            measured_position[reset:] += sensor_rng.normal(0, noise.reset_jump_std, 3) - drift[reset]
            segments[reset:] += 1
        valid &= sensor_rng.random(len(valid)) >= noise.dropout_probability
        if sensor_rng.random() < noise.outage_probability:
            outage_start = sensor_rng.uniform(0.2, 0.7) * duration_s
            valid &= ~((timestamps >= outage_start)
                       & (timestamps < outage_start + noise.outage_duration_s))
    heading = np.arctan2(measured_velocity[:, 1], measured_velocity[:, 0])
    if noisy:
        heading += sensor_rng.normal(0, np.radians(noise.heading_noise_std_deg), len(heading))
    measured_position[~valid] = np.nan
    measured_velocity[~valid] = np.nan
    return SyntheticTrajectory(
        trajectory_id, split, scenario, timestamps, measured_position, measured_velocity,
        np.linalg.norm(measured_velocity, axis=1), np.sin(heading), np.cos(heading),
        valid.astype(np.float32), position, velocity, segments, seed,
    )


def generate_dataset(
    output_dir: str | Path, train_count: int = 70, validation_count: int = 15,
    test_count: int = 15, duration_s: float = 60.0, interval_s: float = 0.1,
    seed: int = 20260927, noise: SensorNoise | None = None,
) -> None:
    from ml.trajectory_provenance import file_hash, write_json
    if min(train_count, validation_count, test_count) < 1:
        raise ValueError("Every split must contain at least one trajectory.")
    noise = noise or SensorNoise()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if list(output_dir.glob("trajectory_*.npz")) or (output_dir / "metadata.json").exists() or (output_dir / "manifest.json").exists():
        raise ValueError("Choose a new output directory; existing trajectory datasets are preserved.")
    rng = np.random.default_rng(seed)
    trajectories, manifest = [], {name: [] for name in ("train", "validation", "test")}
    trajectory_id = 0
    for split, count in (("train", train_count), ("validation", validation_count), ("test", test_count)):
        for split_index in range(count):
            scenario = SCENARIOS[split_index % len(SCENARIOS)]
            trajectory_seed = int(rng.integers(0, 2**32 - 1))
            trajectory = build_trajectory(trajectory_id, split, scenario, duration_s,
                                          interval_s, trajectory_seed, noise=noise)
            path = output_dir / f"trajectory_{trajectory_id:03d}.npz"
            np.savez_compressed(
                path, **asdict(trajectory), coordinate_frame="ENU", schema_version=2,
                sensor_noise_json=json.dumps(asdict(noise)),
            )
            trajectories.append({"trajectory_id": trajectory_id, "split": split,
                                 "scenario": scenario, "seed": trajectory_seed,
                                 "samples": len(trajectory.timestamps), "sha256": file_hash(path)})
            manifest[split].append({"path": path.name, "flight_id": f"synthetic-{trajectory_id}",
                                    "platform": "synthetic", "mission": f"synthetic-{trajectory_id}"})
            trajectory_id += 1
    write_json(output_dir / "metadata.json", {
        "dataset": "synthetic_uav_trajectory_v2", "schema_version": 2, "seed": seed,
        "coordinate_frame": "ENU", "trajectory_count": trajectory_id,
        "train_count": train_count, "validation_count": validation_count, "test_count": test_count,
        "duration_s": duration_s, "interval_s": interval_s, "scenarios": SCENARIOS,
        "sensor_noise": asdict(noise), "noise_calibration": "Illustrative; not calibrated to a real sensor.",
        "label_kind": "simulation_ground_truth", "trajectories": trajectories,
    })
    write_json(output_dir / "manifest.json", manifest)
    print(f"Generated {trajectory_id} ENU trajectories in {output_dir}")


def main(argv=None) -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Generate synthetic UAV flights with separate observations and ground truth.")
    parser.add_argument("--output-dir", default="repository/synthetic_datasets/trajectory_v2")
    parser.add_argument("--train-count", type=int, default=70)
    parser.add_argument("--validation-count", type=int, default=15)
    parser.add_argument("--test-count", type=int, default=15)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=20260927)
    for name, default in asdict(SensorNoise()).items():
        parser.add_argument("--" + name.replace("_", "-"), type=float, default=default)
    args = parser.parse_args(argv)
    noise = SensorNoise(**{name: getattr(args, name) for name in asdict(SensorNoise())})
    generate_dataset(args.output_dir, args.train_count, args.validation_count, args.test_count,
                     args.duration, args.interval, args.seed, noise)


if __name__ == "__main__":
    main()
