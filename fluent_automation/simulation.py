from fluent_automation.config import GuiPauseConfig, SolverConfig, WatertightMeshConfig
from fluent_automation.console import print_color
from fluent_automation.post_processing import PostProcessor
from fluent_automation.solver_setup import SolverConfigurator
from fluent_automation.watertight_meshing import WatertightMesher


class FluentSimulationRunner:
    """Meshing workflowからSolver設定までを順に実行する。"""

    def __init__(
        self,
        mesh_config: WatertightMeshConfig,
        solver_config: SolverConfig,
        pause_config: GuiPauseConfig | None = None,
    ):
        self.mesh_config = mesh_config
        self.solver_config = solver_config
        self.pause_config = pause_config or GuiPauseConfig()
        self.current_session = None

    def run(self):
        meshing_session = WatertightMesher(
            config=self.mesh_config,
            pause_config=self.pause_config,
        ).create()
        self.current_session = meshing_session

        print_color("Start Switch To Solver")
        solver_session = meshing_session.switch_to_solver()
        self.current_session = solver_session
        print_color("End Switch To Solver")

        SolverConfigurator(
            solver_session,
            self.solver_config,
            pause_config=self.pause_config,
        ).setup()
        PostProcessor(solver_session, self.solver_config).generate()
        return solver_session

    def close(self) -> None:
        """現在接続しているFluent sessionを終了する。"""

        if self.current_session is None:
            return

        try:
            self.current_session.exit()
        except Exception:
            try:
                self.current_session.force_exit()
            except Exception:
                pass
        finally:
            self.current_session = None
