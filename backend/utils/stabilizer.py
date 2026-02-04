"""
Heavy Tripod Stabilization Engine
Provides ultra-smooth camera tracking with velocity clamping and exponential smoothing
"""

import math
from typing import Tuple, Optional, List
from dataclasses import dataclass, field

# Lazy import for numpy (not available in production deployment)
np = None

def _ensure_numpy():
    """Lazy load NumPy"""
    global np
    if np is None:
        try:
            import numpy as _np
            np = _np
        except ImportError:
            # Fall back to math module for basic operations
            np = None
    return np

def _sqrt(x):
    """Safe sqrt using numpy if available, else math"""
    if _ensure_numpy() is not None:
        return np.sqrt(x)
    return math.sqrt(x)


@dataclass
class StabilizerConfig:
    """Configuration for the stabilization engine"""
    # Smoothing factor (0-1, higher = more responsive, lower = smoother)
    smoothing_factor: float = 0.15
    # Maximum velocity in pixels per frame
    max_velocity: float = 30.0
    # Lock-on threshold - minimum movement to trigger reframe
    lock_threshold: float = 50.0
    # Acceleration smoothing
    acceleration_smoothing: float = 0.1
    # Deadzone - ignore movements smaller than this
    deadzone: float = 20.0


@dataclass
class TrackingState:
    """Current state of the tracking system"""
    current_x: float = 0.0
    current_y: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    locked: bool = True
    frames_since_detection: int = 0
    position_history: List[Tuple[float, float]] = field(default_factory=list)


class HeavyTripodStabilizer:
    """
    Heavy Tripod Stabilization Engine
    
    Simulates the smooth movement of a heavy camera on a professional tripod.
    Uses exponential smoothing and velocity clamping to eliminate jitter
    while maintaining natural, cinematic camera movement.
    """
    
    def __init__(self, config: Optional[StabilizerConfig] = None):
        self.config = config or StabilizerConfig()
        self.state = TrackingState()
        self.initialized = False
    
    def reset(self, initial_x: float = 0, initial_y: float = 0):
        """Reset the stabilizer state"""
        self.state = TrackingState(
            current_x=initial_x,
            current_y=initial_y,
            target_x=initial_x,
            target_y=initial_y
        )
        self.initialized = True
    
    def update(self, detected_x: float, detected_y: float, 
               confidence: float = 1.0) -> Tuple[float, float]:
        """
        Update tracking with new detection and return smoothed position
        
        Args:
            detected_x: Raw detected X position
            detected_y: Raw detected Y position
            confidence: Detection confidence (0-1)
            
        Returns:
            Tuple of (smoothed_x, smoothed_y)
        """
        if not self.initialized:
            self.reset(detected_x, detected_y)
            return (detected_x, detected_y)
        
        # Update target based on detection
        if confidence > 0.5:
            self.state.target_x = detected_x
            self.state.target_y = detected_y
            self.state.frames_since_detection = 0
        else:
            self.state.frames_since_detection += 1
        
        # Calculate distance to target
        dx = self.state.target_x - self.state.current_x
        dy = self.state.target_y - self.state.current_y
        distance = _sqrt(dx * dx + dy * dy)
        
        # Apply deadzone
        if distance < self.config.deadzone:
            # Store position in history
            self._update_history()
            return (self.state.current_x, self.state.current_y)
        
        # Check lock threshold
        if distance > self.config.lock_threshold:
            self.state.locked = False
        
        if self.state.locked:
            self._update_history()
            return (self.state.current_x, self.state.current_y)
        
        # Calculate desired velocity
        desired_vx = dx * self.config.smoothing_factor
        desired_vy = dy * self.config.smoothing_factor
        
        # Smooth acceleration
        self.state.velocity_x += (desired_vx - self.state.velocity_x) * self.config.acceleration_smoothing
        self.state.velocity_y += (desired_vy - self.state.velocity_y) * self.config.acceleration_smoothing
        
        # Clamp velocity
        velocity_magnitude = _sqrt(
            self.state.velocity_x ** 2 + self.state.velocity_y ** 2
        )
        if velocity_magnitude > self.config.max_velocity:
            scale = self.config.max_velocity / velocity_magnitude
            self.state.velocity_x *= scale
            self.state.velocity_y *= scale
        
        # Apply velocity
        self.state.current_x += self.state.velocity_x
        self.state.current_y += self.state.velocity_y
        
        # Check if we've reached the target (for re-locking)
        new_distance = _sqrt(
            (self.state.target_x - self.state.current_x) ** 2 +
            (self.state.target_y - self.state.current_y) ** 2
        )
        if new_distance < self.config.deadzone:
            self.state.locked = True
            self.state.velocity_x = 0
            self.state.velocity_y = 0
        
        self._update_history()
        return (self.state.current_x, self.state.current_y)
    
    def _update_history(self):
        """Update position history for analysis"""
        self.state.position_history.append(
            (self.state.current_x, self.state.current_y)
        )
        # Keep last 300 frames (~10 seconds at 30fps)
        if len(self.state.position_history) > 300:
            self.state.position_history.pop(0)
    
    def get_smoothed_trajectory(self, 
                                  raw_detections: List[Tuple[float, float, float]]) -> List[Tuple[float, float]]:
        """
        Process a complete trajectory of detections
        
        Args:
            raw_detections: List of (x, y, confidence) tuples
            
        Returns:
            List of smoothed (x, y) positions
        """
        self.reset()
        smoothed = []
        
        for x, y, conf in raw_detections:
            smooth_x, smooth_y = self.update(x, y, conf)
            smoothed.append((smooth_x, smooth_y))
        
        return smoothed
    
    def analyze_movement(self) -> dict:
        """Analyze the movement pattern from history"""
        if len(self.state.position_history) < 2:
            return {"total_movement": 0, "avg_velocity": 0, "is_static": True}
        
        positions = np.array(self.state.position_history)
        deltas = np.diff(positions, axis=0)
        distances = np.sqrt(np.sum(deltas ** 2, axis=1))
        
        return {
            "total_movement": float(np.sum(distances)),
            "avg_velocity": float(np.mean(distances)),
            "max_velocity": float(np.max(distances)),
            "is_static": float(np.mean(distances)) < 5.0
        }
