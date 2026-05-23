from fluent_automation.config import GuiPauseConfig, SolverConfig
from fluent_automation.console import pause_for_gui, print_color
from fluent_automation.pyfluent_helpers import set_constant_value, set_state


class SolverConfigurator:
    """Solver sessionへ物理モデル・境界条件・初期化条件を設定する。"""

    def __init__(
        self,
        solver_session,
        config: SolverConfig,
        pause_config: GuiPauseConfig | None = None,
    ):
        self.solver_session = solver_session
        self.config = config
        self.pause_config = pause_config or GuiPauseConfig()

    def setup(self) -> None:
        """Meshingから切り替えたSolver sessionへ基本設定を投入する。"""

        print_color("Start Solver Setup")
        self._setup_units()
        self._perform_mesh_check()
        self._setup_models()
        self._setup_materials()
        self._setup_cell_zones()
        self._setup_boundaries()
        print_color("End Solver Setup")

        if self.pause_config.enabled and self.pause_config.before_solver_run:
            pause_for_gui("Solver設定が完了しました。解析を開始する前にFluent GUIで確認してください。")

        if self.config.initialize:
            self._initialize()

        self._run_iterations()

    def _setup_units(self) -> None:
        """Set Unitsでlengthの表示単位を設定する。"""

        if not self.config.set_length_unit:
            return

        print_color(f"Start Set Units: length -> {self.config.length_unit}")
        try:
            self.solver_session.settings.setup.units_settings.new_unit(
                quantity="length",
                units_name=self.config.length_unit,
                scale_factor=self.config.length_unit_scale_factor,
                offset=self.config.length_unit_offset,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to set length unit: {self.config.length_unit}"
            ) from exc
        print_color(f"End Set Units: length -> {self.config.length_unit}")

    def _perform_mesh_check(self) -> None:
        """Solver modeでmesh checkを実行する。"""

        if not self.config.perform_mesh_check:
            return

        print_color("Start Mesh Check")
        try:
            self.solver_session.settings.mesh.check()
        except Exception as exc:
            raise RuntimeError("Failed to perform mesh check.") from exc
        print_color("End Mesh Check")

    def _setup_models(self) -> None:
        """Solverの物理モデルを設定する。"""

        setup = self.solver_session.settings.setup
        set_state(
            setup.models.energy.enabled,
            self.config.energy_enabled,
            "setup.models.energy.enabled",
        )

        if self.config.viscous_model:
            set_state(
                setup.models.viscous.model,
                self.config.viscous_model,
                "setup.models.viscous.model",
            )
        if self.config.k_omega_model:
            set_state(
                setup.models.viscous.k_omega_model,
                self.config.k_omega_model,
                "setup.models.viscous.k_omega_model",
            )

    def _setup_materials(self) -> None:
        """Fluent databaseから材料をコピーする。"""

        material_name = self.config.database_material_name
        print_color(f"Start Copy Material: {material_name}")
        materials = self.solver_session.settings.setup.materials
        try:
            materials.database.copy_by_name(
                type=self.config.database_material_type,
                name=material_name,
            )
        except Exception as exc:
            if self._material_exists(materials, material_name):
                print_color(f"Material already exists: {material_name}", color="yellow")
            else:
                raise RuntimeError(f"Failed to copy material: {material_name}") from exc
        print_color(f"End Copy Material: {material_name}")

    def _material_exists(self, materials, material_name: str) -> bool:
        try:
            return material_name in materials.fluid.get_object_names()
        except Exception:
            return False

    def _setup_cell_zones(self) -> None:
        """Fluid cell zoneの材料を設定する。"""

        cell_zone_conditions = self.solver_session.settings.setup.cell_zone_conditions
        zone_name = self._resolve_fluid_cell_zone_name(cell_zone_conditions)
        material_name = self.config.fluid_cell_zone_material

        print_color(f"Start Set Cell Zone Material: {zone_name} -> {material_name}")
        fluid_zone = cell_zone_conditions.fluid[zone_name]
        set_state(
            fluid_zone.general.material,
            material_name,
            f"cell_zone_conditions.fluid[{zone_name}].general.material",
        )
        print_color(f"End Set Cell Zone Material: {zone_name} -> {material_name}")

    def _resolve_fluid_cell_zone_name(self, cell_zone_conditions) -> str:
        configured_name = self.config.fluid_cell_zone_name
        try:
            fluid_zone_names = cell_zone_conditions.fluid.get_object_names()
        except Exception as exc:
            raise RuntimeError("Failed to get fluid cell zone names.") from exc

        if configured_name in fluid_zone_names:
            return configured_name
        if len(fluid_zone_names) == 1:
            only_zone = fluid_zone_names[0]
            print_color(
                f"Configured fluid zone '{configured_name}' was not found. "
                f"Using the only fluid zone: {only_zone}",
                color="yellow",
            )
            return only_zone

        raise RuntimeError(
            f"Fluid cell zone '{configured_name}' was not found. "
            f"Available fluid zones: {fluid_zone_names}"
        )

    def _setup_boundaries(self) -> None:
        """Cappingで作った入口/出口へSolver側の境界条件を入れる。"""

        boundary_conditions = self.solver_session.settings.setup.boundary_conditions
        self._setup_velocity_inlet(boundary_conditions)
        self._setup_pressure_outlet(boundary_conditions)

    def _setup_velocity_inlet(self, boundary_conditions) -> None:
        inlet = self.config.velocity_inlet
        if inlet is None:
            return

        velocity_inlet = boundary_conditions.velocity_inlet[inlet.name]
        velocity_inlet_settings = getattr(velocity_inlet, "settings", velocity_inlet)
        momentum = velocity_inlet_settings.momentum
        turbulence = velocity_inlet_settings.turbulence
        thermal = velocity_inlet_settings.thermal

        if inlet.velocity_specification_method is not None:
            set_state(
                momentum.velocity_specification_method,
                inlet.velocity_specification_method,
                f"velocity_inlet[{inlet.name}].velocity_specification_method",
            )
        if inlet.velocity_magnitude is not None:
            set_constant_value(
                momentum.velocity_magnitude,
                inlet.velocity_magnitude,
                f"velocity_inlet[{inlet.name}].velocity_magnitude",
            )
        if inlet.turbulence_specification is not None:
            set_state(
                turbulence.turbulence_specification,
                inlet.turbulence_specification,
                f"velocity_inlet[{inlet.name}].turbulence_specification",
            )
        if inlet.turbulent_intensity is not None:
            set_state(
                turbulence.turbulent_intensity,
                inlet.turbulent_intensity,
                f"velocity_inlet[{inlet.name}].turbulent_intensity",
            )
        if inlet.hydraulic_diameter is not None:
            set_state(
                turbulence.hydraulic_diameter,
                inlet.hydraulic_diameter,
                f"velocity_inlet[{inlet.name}].hydraulic_diameter",
            )
        if self.config.energy_enabled and inlet.temperature is not None:
            temperature_setting = self._first_available_setting(
                thermal,
                names=("temperature", "total_temperature"),
                label=f"velocity_inlet[{inlet.name}].thermal temperature",
            )
            set_constant_value(
                temperature_setting,
                inlet.temperature,
                f"velocity_inlet[{inlet.name}].temperature",
            )

    def _setup_pressure_outlet(self, boundary_conditions) -> None:
        outlet = self.config.pressure_outlet
        if outlet is None:
            return

        pressure_outlet = boundary_conditions.pressure_outlet[outlet.name]
        pressure_outlet_settings = getattr(pressure_outlet, "settings", pressure_outlet)
        momentum = pressure_outlet_settings.momentum
        turbulence = pressure_outlet_settings.turbulence
        thermal = pressure_outlet_settings.thermal

        if outlet.gauge_pressure is not None:
            set_constant_value(
                momentum.gauge_pressure,
                outlet.gauge_pressure,
                f"pressure_outlet[{outlet.name}].gauge_pressure",
            )
        if outlet.turbulence_specification is not None:
            set_state(
                turbulence.turbulence_specification,
                outlet.turbulence_specification,
                f"pressure_outlet[{outlet.name}].turbulence_specification",
            )
        if outlet.turbulent_intensity is not None:
            turbulent_intensity_setting = self._first_available_setting(
                turbulence,
                names=("backflow_turbulent_intensity", "turbulent_intensity"),
                label=f"pressure_outlet[{outlet.name}].turbulent_intensity",
            )
            set_state(
                turbulent_intensity_setting,
                outlet.turbulent_intensity,
                f"pressure_outlet[{outlet.name}].turbulent_intensity",
            )
        if outlet.hydraulic_diameter is not None:
            hydraulic_diameter_setting = self._first_available_setting(
                turbulence,
                names=("backflow_hydraulic_diameter", "hydraulic_diameter"),
                label=f"pressure_outlet[{outlet.name}].hydraulic_diameter",
            )
            set_state(
                hydraulic_diameter_setting,
                outlet.hydraulic_diameter,
                f"pressure_outlet[{outlet.name}].hydraulic_diameter",
            )
        if self.config.energy_enabled and outlet.backflow_temperature is not None:
            backflow_temperature_setting = self._first_available_setting(
                thermal,
                names=("backflow_total_temperature", "backflow_temperature"),
                label=f"pressure_outlet[{outlet.name}].thermal backflow temperature",
            )
            set_constant_value(
                backflow_temperature_setting,
                outlet.backflow_temperature,
                f"pressure_outlet[{outlet.name}].backflow_total_temperature",
            )

    def _first_available_setting(
        self,
        parent,
        names: tuple[str, ...],
        label: str,
    ):
        for name in names:
            if hasattr(parent, name):
                return getattr(parent, name)

        raise RuntimeError(
            f"Failed to find solver setting: {label}. Tried: {', '.join(names)}"
        )

    def _initialize(self) -> None:
        """Hybrid initializationを実行する。"""

        print_color("Start Solver Initialize")
        self.solver_session.settings.solution.initialization.hybrid_initialize()
        print_color("End Solver Initialize")

    def _run_iterations(self) -> None:
        """指定回数だけSolverを反復する。0以下なら実行しない。"""

        if self.config.iterations <= 0:
            return

        print_color("Start Solver Iterate")
        self.solver_session.settings.solution.run_calculation.iterate(
            iter_count=self.config.iterations
        )
        print_color("End Solver Iterate")
