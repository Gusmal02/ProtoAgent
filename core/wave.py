"""
Ecuación de onda discreta sobre el campo de perturbación.
∂²ε_i/∂t² = −Σ_{j∈N(i)} w_{ij}(ε_i − ε_j) − α ∂ε_i/∂t

Permite medir propagación con velocidad finita, en contraste con difusión.
"""

import torch


class WaveField:
    """
    Campo de onda escalar sobre grafo.
    ε_i(t) = perturbación (escalar por nodo) sobre el atractor.
    """

    def __init__(
        self,
        N: int,
        edge_index: torch.Tensor,
        edge_weight: torch.Tensor | None = None,
        alpha_damp: float = 0.1,
        dt: float = 0.05,
        device: str = "cpu",
    ):
        self.N = N
        self.alpha_damp = alpha_damp
        self.dt = dt
        self.device = device

        self.edge_index = edge_index.to(device)
        if edge_weight is None:
            self.edge_weight = torch.ones(edge_index.shape[1], device=device)
        else:
            self.edge_weight = edge_weight.to(device)

        self.eps = torch.zeros(N, device=device)      # ε_i
        self.eps_vel = torch.zeros(N, device=device)  # ∂ε_i/∂t

    def _laplacian_term(self) -> torch.Tensor:
        """−Σ_{j∈N(i)} w_{ij}(ε_i − ε_j) para cada i."""
        src, dst = self.edge_index[0], self.edge_index[1]
        diff = self.eps[dst] - self.eps[src]          # ε_j − ε_i  (desde i hacia j)
        flux = torch.zeros(self.N, device=self.device)
        flux.index_add_(0, src, self.edge_weight * diff)
        return flux

    def step(self):
        lap = self._laplacian_term()
        acc = lap - self.alpha_damp * self.eps_vel    # aceleración
        self.eps_vel = self.eps_vel + self.dt * acc
        self.eps = self.eps + self.dt * self.eps_vel

    def perturb(self, node_idx: int, amplitude: float):
        """Introduce una perturbación impulsiva en el nodo node_idx."""
        self.eps[node_idx] += amplitude

    def energy(self) -> torch.Tensor:
        """Energía total del campo de onda (observable de propagación)."""
        return 0.5 * (self.eps_vel ** 2 + self.eps ** 2)
