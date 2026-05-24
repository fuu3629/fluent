from dataclasses import dataclass, field


GEOMETRY_SETUP_ONLY_SOLID = "The geometry consists of only solid regions"
GEOMETRY_SETUP_ONLY_FLUID = "The geometry consists of only fluid regions with no voids"
GEOMETRY_SETUP_FLUID_AND_SOLID = (
    "The geometry consists of both fluid and solid regions and/or voids"
)


@dataclass
class CapSetting:
    """Enclose Fluid Regions (Capping)で作成するcapの設定。"""

    name: str
    zone_type: str
    selection_type: str
    zones: list[str]


@dataclass
class BoundaryLayerSetting:
    """Add Boundary Layersで作成する境界層制御の設定。"""

    control_name: str
    regions_type: str | None = None
    region_scope: list[str] | None = None
    number_of_layers: int | None = None


@dataclass
class BoundaryTypeSetting:
    """Update BoundariesでSolverへ渡す境界名・境界タイプの設定。"""

    name: str
    zone_type: str
    zones: list[str]
    selection_type: str = "zone"
    old_name: str | None = None
    old_zone_type: str | None = None


@dataclass
class GuiPauseConfig:
    """Fluent GUI確認用の一時停止設定。"""

    enabled: bool = False
    after_surface_mesh: bool = True
    after_update_boundaries: bool = True
    after_update_regions: bool = True
    after_boundary_layers: bool = True
    after_volume_mesh: bool = True
    before_solver_run: bool = True


@dataclass
class WatertightMeshConfig:
    """Watertight Geometry workflowに投入する設定。"""

    geometry_file: str | None = None
    run_directory: str = "output"
    cleanup_on_exit: bool = False
    length_unit: str = "mm"
    surface_max_size: float = 0.3
    separation_required: bool = True
    separation_angle: float = 40.0
    capping_required: bool = True
    geometry_setup_type: str = GEOMETRY_SETUP_ONLY_SOLID
    wall_to_internal: bool = False
    cap_settings: list[CapSetting] = field(default_factory=lambda: [
        CapSetting(
            name="velo-inlet_1",
            zone_type="velocity-inlet",
            selection_type="zone",
            zones=["document-brep_1:1:12"],
        ),
        CapSetting(
            name="pres_outlet_1",
            zone_type="pressure-outlet",
            selection_type="zone",
            zones=["document-brep_1:1:14"],
        ),
    ])
    boundary_type_settings: list[BoundaryTypeSetting] = field(default_factory=lambda: [
        BoundaryTypeSetting(
            name="document-brep_1:1:15",
            zone_type="wall",
            zones=["document-brep_1:1:15"],
            old_name="document-brep_1",
            old_zone_type="wall",
        ),
    ])
    number_of_flow_volumes: int = 1
    retain_dead_region_name: bool = False
    volume_fill: str = "poly-hexcore"
    processor_count: int = 2
    boundary_layers: list[BoundaryLayerSetting] = field(default_factory=lambda: [
        BoundaryLayerSetting(control_name="smooth-transition_1"),
        BoundaryLayerSetting(
            control_name="smooth-transition_2",
            regions_type="solid-regions",
            number_of_layers=1,
        ),
    ])


@dataclass
class VelocityInletSetting:
    """Solverでvelocity-inletへ入れる境界条件。"""

    name: str = "velo-inlet_1"
    velocity_specification_method: str | None = "Magnitude, Normal to Boundary"
    velocity_magnitude: float | None = 0.4
    turbulence_specification: str | None = "Intensity and Hydraulic Diameter"
    turbulent_intensity: float | None = None
    hydraulic_diameter: float | None = 100.0
    temperature: float | None = 293.15


@dataclass
class PressureOutletSetting:
    """Solverでpressure-outletへ入れる境界条件。"""

    name: str = "pres_outlet_1"
    gauge_pressure: float | None = 0.0
    turbulence_specification: str | None = "Intensity and Hydraulic Diameter"
    turbulent_intensity: float | None = None
    hydraulic_diameter: float | None = 100.0
    backflow_temperature: float | None = 300.0


@dataclass
class SolverConfig:
    """Meshingから切り替えたSolver sessionへ投入する設定。"""

    set_length_unit: bool = True
    length_unit: str = "mm"
    length_unit_scale_factor: float = 0.001
    length_unit_offset: float = 0.0
    perform_mesh_check: bool = True
    energy_enabled: bool = True
    viscous_model: str | None = "k-omega"
    k_omega_model: str | None = None
    database_material_type: str = "fluid"
    database_material_name: str = "water-liquid"
    fluid_cell_zone_name: str = "fluid"
    fluid_cell_zone_material: str = "water-liquid"
    velocity_inlet: VelocityInletSetting | None = field(
        default_factory=VelocityInletSetting
    )
    pressure_outlet: PressureOutletSetting | None = field(
        default_factory=PressureOutletSetting
    )
    initialize: bool = True
    iterations: int = 200
    post_processing: "PostProcessingConfig" = field(
        default_factory=lambda: PostProcessingConfig()
    )


@dataclass
class ContourImageSetting:
    """解析後に保存するコンター画像の設定。"""

    name: str
    field: str
    file_name: str
    surfaces: list[str] | None = None


@dataclass
class PostProcessingConfig:
    """解析後のレポート・画像出力設定。"""

    enabled: bool = True
    output_dir: str = "output"
    report_file_name: str = "thermal_report.md"
    save_case_data: bool = True
    case_data_file_name: str = "solution.cas.h5"
    contour_images: list[ContourImageSetting] = field(default_factory=lambda: [
        ContourImageSetting(
            name="temperature-contour",
            field="temperature",
            file_name="temperature_contour.png",
        ),
        ContourImageSetting(
            name="velocity-contour",
            field="velocity-magnitude",
            file_name="velocity_contour.png",
        ),
    ])
