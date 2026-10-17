"""WorldModel empírico mínimo: predicción local con incertidumbre explícita."""

from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np


@dataclass
class Transition:
    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    terminal: bool
    # La versión codificada sirve para hallar vecinos.  La observación cruda
    # preserva las variables que un planificador debe poder proyectar.
    raw_next_state: np.ndarray | None = None


class EmpiricalWorldModel:
    """Memoria local de transiciones; no inventa certeza fuera de cobertura."""

    def __init__(self, distance_scale: float = 1.0, state_encoder=None):
        self.distance_scale = distance_scale
        self.state_encoder = state_encoder
        self.transitions: list[Transition] = []
        self._prediction_cache: dict[tuple[tuple[float, ...], int, int], dict] = {}
        self._index: dict[int, dict[str, np.ndarray]] | None = None

    def _encode_state(self, state) -> np.ndarray:
        raw = np.asarray(state, dtype=np.float32)
        return np.asarray(self.state_encoder(raw), dtype=np.float32) if self.state_encoder else raw

    def observe(self, state, action, reward, next_state, terminal) -> None:
        self._prediction_cache.clear()
        self._index = None
        self.transitions.append(Transition(
            self._encode_state(state).copy(), int(action), float(reward),
            self._encode_state(next_state).copy(), bool(terminal),
            np.asarray(next_state, dtype=np.float32).copy(),
        ))

    def prepare(self) -> None:
        """Congela un índice vectorizado para campañas de evaluación.

        No cambia ninguna transición; sólo evita que una búsqueda causal pague
        de nuevo el coste lineal de recorrer toda su historia por cada rama.
        """
        index: dict[int, dict[str, np.ndarray]] = {}
        for action in sorted({t.action for t in self.transitions}):
            rows = [t for t in self.transitions if t.action == action]
            index[action] = {
                "state": np.stack([t.state for t in rows]),
                "reward": np.asarray([t.reward for t in rows], dtype=np.float32),
                "next": np.stack([t.next_state for t in rows]),
                "raw_next": np.stack([t.raw_next_state if t.raw_next_state is not None else t.next_state for t in rows]),
                "terminal": np.asarray([float(t.terminal) for t in rows], dtype=np.float32),
            }
        self._index = index
        self._prediction_cache.clear()

    def predict(self, state, action, k: int = 5) -> dict:
        state = self._encode_state(state)
        key = (tuple(np.round(state, 4).tolist()), int(action), int(k))
        if key in self._prediction_cache:
            return self._prediction_cache[key]
        packed = self._index.get(int(action)) if self._index is not None else None
        matches = None if packed is not None else [t for t in self.transitions if t.action == int(action)]
        if packed is None and not matches:
            result = {"known": False, "reward": 0.0, "uncertainty": 1.0, "support": 0}
            self._prediction_cache[key] = result
            return result
        states = packed["state"] if packed is not None else np.stack([t.state for t in matches])
        distances = np.linalg.norm(states - state, axis=1)
        # A igual distancia contextual, priorizar la observación más reciente.
        n_available = len(states)
        idx = np.array(sorted(range(n_available), key=lambda i: (distances[i], -i))[:min(k, n_available)])
        # La evidencia reciente pesa más: una ley que cambió debe poder desplazar
        # una memoria antigua en vez de quedar promediada eternamente con ella.
        n_matches = len(states)
        ages = np.array([n_matches - 1 - int(i) for i in idx])
        weights = np.exp(-distances[idx] / max(self.distance_scale, 1e-6)) * np.exp(-0.35 * ages) + 1e-8
        rewards = packed["reward"][idx] if packed is not None else np.array([matches[i].reward for i in idx])
        mean = float(np.average(rewards, weights=weights))
        spread = float(np.sqrt(np.average((rewards - mean) ** 2, weights=weights)))
        coverage = float(np.mean(distances[idx]))
        next_encoded = packed["next"][idx] if packed is not None else np.stack([matches[i].next_state for i in idx])
        next_state = np.average(next_encoded, axis=0, weights=weights).astype(np.float32)
        # Las transiciones antiguas (sin raw_next_state) siguen siendo legibles.
        raw_states = packed["raw_next"][idx] if packed is not None else np.stack([matches[i].raw_next_state if matches[i].raw_next_state is not None else matches[i].next_state for i in idx])
        raw_next_state = np.average(raw_states, axis=0, weights=weights).astype(np.float32)
        next_spread = float(np.sqrt(np.average(
            np.sum((next_encoded - next_state) ** 2, axis=1), weights=weights
        )))
        terminal_probability = float(np.average(
            (packed["terminal"][idx] if packed is not None else np.asarray([float(matches[i].terminal) for i in idx])), weights=weights
        ))
        # Incertidumbre = variación observada + lejanía + escasez de evidencia.
        uncertainty = min(1.0, spread + next_spread + coverage / self.distance_scale + 1 / math.sqrt(len(idx)))
        result = {
            "known": True, "reward": mean, "reward_spread": spread,
            "next_state": next_state, "raw_next_state": raw_next_state,
            "next_state_spread": next_spread,
            "terminal_probability": terminal_probability,
            "uncertainty": uncertainty, "support": len(idx),
        }
        self._prediction_cache[key] = result
        return result

    def summary(self) -> dict:
        return {"transitions": len(self.transitions), "actions_seen": sorted({t.action for t in self.transitions})}
