/**
 * NavigationController
 *
 * Lightweight, dependency-free navigation state coordinator.
 * Implements a strictly monotonic `navId` state machine so rapid successive
 * navigations (e.g. Options -> Signals -> Crypto in <1s) never allow delayed
 * transition completions or timeouts from older navigations to prematurely
 * cancel or freeze the active progress indicator.
 */

export type NavigationState = {
  activeNavId: number;
  isNavigating: boolean;
};

class NavigationController {
  private currentNavId = 0;
  private isNavigating = false;
  private timeoutId: ReturnType<typeof setTimeout> | null = null;
  private listeners = new Set<(state: NavigationState) => void>();

  /**
   * Start a navigation. Must be called synchronously in the click/keyboard
   * event handler before router transition begins.
   */
  start(): number {
    this.currentNavId += 1;
    const navId = this.currentNavId;
    this.isNavigating = true;
    this.resetTimeout(navId);
    this.notify();
    return navId;
  }

  /**
   * Complete a navigation. If navId is provided and does not match the latest
   * active navigation, the completion event is safely discarded.
   */
  complete(navId?: number): void {
    if (navId !== undefined && navId !== this.currentNavId) {
      // Stale completion event from an older navigation — ignore
      return;
    }
    this.clearTimeout();
    this.isNavigating = false;
    this.notify();
  }

  /**
   * Cancel the active navigation.
   */
  cancel(navId?: number): void {
    if (navId !== undefined && navId !== this.currentNavId) return;
    this.clearTimeout();
    this.isNavigating = false;
    this.notify();
  }

  /**
   * Current navigation state snapshot.
   */
  getState(): NavigationState {
    return {
      activeNavId: this.currentNavId,
      isNavigating: this.isNavigating,
    };
  }

  /**
   * Subscribe to navigation state changes.
   */
  subscribe(listener: (state: NavigationState) => void): () => void {
    this.listeners.add(listener);
    listener(this.getState());
    return () => {
      this.listeners.delete(listener);
    };
  }

  // 8-second emergency fallback timeout to prevent stuck indicator on network error
  private resetTimeout(navId: number): void {
    this.clearTimeout();
    this.timeoutId = setTimeout(() => {
      if (this.currentNavId === navId && this.isNavigating) {
        this.isNavigating = false;
        this.notify();
      }
    }, 8000);
  }

  private clearTimeout(): void {
    if (this.timeoutId) {
      clearTimeout(this.timeoutId);
      this.timeoutId = null;
    }
  }

  private notify(): void {
    const state = this.getState();
    this.listeners.forEach((fn) => fn(state));
  }
}

// Module-level singleton
export const navigationController = new NavigationController();
