from pathlib import Path
from typing import Any, Callable

from ansys.fluent.core.solver import Contour

from fluent_automation.config import ContourImageSetting, PostProcessingConfig, SolverConfig
from fluent_automation.console import print_color


class PostProcessor:
    """解析結果のレポートと画像を出力する。"""

    def __init__(self, solver_session, solver_config: SolverConfig):
        self.solver_session = solver_session
        self.solver_config = solver_config
        self.config: PostProcessingConfig = solver_config.post_processing
        self.output_dir = Path(self.config.output_dir).resolve()

    def generate(self) -> None:
        if not self.config.enabled:
            return

        print_color("Start Post Processing")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        case_data_path = self._save_case_data()
        image_paths = self._save_contour_images()
        self._write_report(case_data_path=case_data_path, image_paths=image_paths)
        print_color("End Post Processing")

    def _save_case_data(self) -> Path | None:
        if not self.config.save_case_data:
            return None

        case_data_path = self.output_dir / self.config.case_data_file_name
        try:
            self.solver_session.settings.file.write_case_data(
                file_name=str(case_data_path)
            )
            return case_data_path
        except Exception as exc:
            print_color(f"Failed to save case/data: {exc}", color="yellow")
            return None

    def _save_contour_images(self) -> list[Path]:
        image_paths: list[Path] = []
        for image_setting in self.config.contour_images:
            image_path = self._save_contour_image(image_setting)
            if image_path is not None:
                image_paths.append(image_path)

        return image_paths

    def _save_contour_image(self, image_setting: ContourImageSetting) -> Path | None:
        image_path = self.output_dir / image_setting.file_name
        try:
            contour = Contour(
                self.solver_session,
                new_instance_name=image_setting.name,
            )
            contour.field = image_setting.field
            contour.surfaces_list = self._resolve_contour_surfaces(
                contour=contour,
                configured_surfaces=image_setting.surfaces,
            )
            contour.colorings.banded = True
            contour.display()

            graphics = self.solver_session.settings.results.graphics
            graphics.views.auto_scale()
            graphics.picture.save_picture(file_name=str(image_path))
            return image_path
        except Exception as exc:
            print_color(
                f"Failed to save contour image '{image_setting.file_name}': {exc}",
                color="yellow",
            )
            return None

    def _resolve_contour_surfaces(
        self,
        contour,
        configured_surfaces: list[str] | None,
    ) -> list[str]:
        if configured_surfaces is not None:
            return configured_surfaces

        allowed_surfaces = contour.surfaces_list.allowed_values()
        if not allowed_surfaces:
            raise RuntimeError("No surfaces are available for contour output.")

        return allowed_surfaces

    def _write_report(
        self,
        case_data_path: Path | None,
        image_paths: list[Path],
    ) -> None:
        report_path = self.output_dir / self.config.report_file_name
        lines = [
            "# Thermal Analysis Report",
            "",
            "## Solver Settings",
            "",
            f"- Length unit: {self.solver_config.length_unit}",
            f"- Energy equation: {self.solver_config.energy_enabled}",
            f"- Viscous model: {self.solver_config.viscous_model}",
            f"- K-omega model: {self.solver_config.k_omega_model or 'Fluent default'}",
            f"- Material: {self.solver_config.fluid_cell_zone_material}",
            f"- Iterations: {self.solver_config.iterations}",
            "",
            "## Boundary Conditions",
            "",
        ]

        inlet = self.solver_config.velocity_inlet
        if inlet is not None:
            lines.extend(
                [
                    f"- Inlet: {inlet.name}",
                    f"- Velocity specification: {inlet.velocity_specification_method}",
                    f"- Velocity magnitude: {inlet.velocity_magnitude} m/s",
                    f"- Turbulence specification: {inlet.turbulence_specification}",
                    f"- Hydraulic diameter: {inlet.hydraulic_diameter}",
                    f"- Temperature: {inlet.temperature} K",
                    "",
                ]
            )

        outlet = self.solver_config.pressure_outlet
        if outlet is not None:
            lines.extend(
                [
                    f"- Outlet: {outlet.name}",
                    f"- Gauge pressure: {outlet.gauge_pressure} Pa",
                    f"- Turbulence specification: {outlet.turbulence_specification}",
                    f"- Hydraulic diameter: {outlet.hydraulic_diameter}",
                    f"- Backflow total temperature: {outlet.backflow_temperature} K",
                    "",
                ]
            )

        lines.extend(["## Result Summary", ""])
        lines.extend(self._report_metrics())

        lines.extend(["", "## Output Files", ""])
        if case_data_path is not None:
            lines.append(f"- Case/data: `{case_data_path}`")
        for image_path in image_paths:
            lines.append(f"- Image: `{image_path}`")

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _report_metrics(self) -> list[str]:
        outlet_name = (
            self.solver_config.pressure_outlet.name
            if self.solver_config.pressure_outlet is not None
            else None
        )
        inlet_name = (
            self.solver_config.velocity_inlet.name
            if self.solver_config.velocity_inlet is not None
            else None
        )

        lines = [
            self._format_metric(
                "Total sensible heat transfer",
                lambda: self.solver_session.settings.results.report.fluxes.get_heat_transfer_sensible(
                    zones="*"
                ),
            )
        ]

        if inlet_name is not None:
            lines.extend(
                [
                    self._format_surface_metric(
                        "Inlet area-weighted temperature",
                        "temperature",
                        "get_area_weighted_avg",
                        inlet_name,
                    ),
                    self._format_mass_flow_rate(
                        "Inlet mass flow rate",
                        inlet_name,
                    ),
                ]
            )

        if outlet_name is not None:
            lines.extend(
                [
                    self._format_surface_metric(
                        "Outlet mass-weighted temperature",
                        "temperature",
                        "get_mass_weighted_avg",
                        outlet_name,
                    ),
                    self._format_surface_metric(
                        "Outlet area-weighted velocity",
                        "velocity-magnitude",
                        "get_area_weighted_avg",
                        outlet_name,
                    ),
                    self._format_mass_flow_rate(
                        "Outlet mass flow rate",
                        outlet_name,
                    ),
                ]
            )

        return lines

    def _format_surface_metric(
        self,
        label: str,
        report_of: str,
        method_name: str,
        surface_name: str,
    ) -> str:
        surface_integrals = self.solver_session.settings.results.report.surface_integrals
        method = getattr(surface_integrals, method_name)
        return self._format_metric(
            label,
            lambda: method(report_of=report_of, surface_names=[surface_name]),
        )

    def _format_mass_flow_rate(self, label: str, surface_name: str) -> str:
        surface_integrals = self.solver_session.settings.results.report.surface_integrals
        return self._format_metric(
            label,
            lambda: surface_integrals.get_mass_flow_rate(surface_names=[surface_name]),
        )

    def _format_metric(self, label: str, getter: Callable[[], Any]) -> str:
        try:
            value = getter()
            return f"- {label}: `{value}`"
        except Exception as exc:
            return f"- {label}: unavailable (`{exc}`)"
