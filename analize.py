from fluent_automation.config import (
    GEOMETRY_SETUP_ONLY_SOLID,
    GuiPauseConfig,
    PostProcessingConfig,
    PressureOutletSetting,
    SolverConfig,
    VelocityInletSetting,
    WatertightMeshConfig,
)
from fluent_automation.post_processing import write_failure_metrics
from fluent_automation.simulation import FluentSimulationRunner


mesh_config = WatertightMeshConfig(
    geometry_file="heatsink-rasen-no-self3.stp",  # Noneなら mixing_elbow.pmdb を使用
    run_directory="output",
    cleanup_on_exit=False,
    length_unit="mm",
    surface_max_size=3,
    separation_required=True,
    separation_angle=40.0,
    geometry_setup_type=GEOMETRY_SETUP_ONLY_SOLID,
    volume_fill="poly-hexcore",
    processor_count=2,
)

gui_pause_config = GuiPauseConfig(
    enabled=True,
    after_surface_mesh=False,
    after_update_regions=False,
    after_boundary_layers=False,
    after_volume_mesh=False,
    before_solver_run=True,
)

solver_config = SolverConfig(
    set_length_unit=True,
    length_unit="mm",
    length_unit_scale_factor=0.001,
    length_unit_offset=0.0,
    perform_mesh_check=True,
    energy_enabled=True,
    viscous_model="k-omega",
    k_omega_model=None,
    database_material_name="water-liquid",
    fluid_cell_zone_name="fluid",
    fluid_cell_zone_material="water-liquid",
    velocity_inlet=VelocityInletSetting(
        name="velo-inlet_1",
        velocity_specification_method="Magnitude, Normal to Boundary",
        velocity_magnitude=0.4,
        turbulence_specification="Intensity and Hydraulic Diameter",
        hydraulic_diameter=100.0,
        temperature=293.15,
    ),
    pressure_outlet=PressureOutletSetting(
        name="pres_outlet_1",
        gauge_pressure=0.0,
        turbulence_specification="Intensity and Hydraulic Diameter",
        hydraulic_diameter=100.0,
        backflow_temperature=None,
    ),
    initialize=True,
    iterations=100,
    post_processing=PostProcessingConfig(
        enabled=True,
        output_dir="output",
    ),
)


if __name__ == "__main__":
    runner = FluentSimulationRunner(
        mesh_config=mesh_config,
        solver_config=solver_config,
        pause_config=gui_pause_config,
    )
    try:
        runner.run()
    except Exception as exc:
        print(f"\nError: {exc}")
        metrics_path = write_failure_metrics(solver_config, str(exc))
        if metrics_path is not None:
            print(f"Failure metrics were written to: {metrics_path}")
        runner.close()
    else:
        runner.close()
