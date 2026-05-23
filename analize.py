from fluent_automation.config import (
    GEOMETRY_SETUP_ONLY_SOLID,
    PostProcessingConfig,
    SolverConfig,
    VelocityInletSetting,
    WatertightMeshConfig,
)
from fluent_automation.simulation import FluentSimulationRunner


mesh_config = WatertightMeshConfig(
    geometry_file="heatsink-rasen-no-self3.stp",  # Noneなら mixing_elbow.pmdb を使用
    length_unit="mm",
    surface_max_size=3,
    separation_required=True,
    separation_angle=40.0,
    geometry_setup_type=GEOMETRY_SETUP_ONLY_SOLID,
    pause_after_surface_mesh=True,
    volume_fill="poly-hexcore",
    processor_count=2,
)

solver_config = SolverConfig(
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
        hydraulic_diameter="100 [mm]",
        temperature=293.15,
    ),
    initialize=True,
    iterations=200,
    post_processing=PostProcessingConfig(
        enabled=True,
        output_dir="outputs",
    ),
)


if __name__ == "__main__":
    FluentSimulationRunner(
        mesh_config=mesh_config,
        solver_config=solver_config,
    ).run()
