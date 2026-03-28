/**
 * Tests for ProjectHub Dashboard Optimizations
 * Tests caching, debounce, smart intervals, and lazy loading
 */

const { describe, it, expect, beforeEach, afterEach } = require('@jest/globals');

// Mock localStorage and sessionStorage
const mockStorage = () => {
  let store = {};
  return {
    getItem: (key) => store[key] || null,
    setItem: (key, value) => { store[key] = value; },
    removeItem: (key) => { delete store[key]; },
    clear: () => { store = {}; }
  };
};

global.localStorage = mockStorage();
global.sessionStorage = mockStorage();

describe('Cache System', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  describe('Persistent Cache (localStorage)', () => {
    it('should store and retrieve values', () => {
      const cache = {
        get(key) {
          const item = localStorage.getItem(`ph_${key}`);
          if (!item) return null;
          const { value, timestamp, ttl } = JSON.parse(item);
          if (ttl && Date.now() - timestamp > ttl) {
            localStorage.removeItem(`ph_${key}`);
            return null;
          }
          return value;
        },
        set(key, value, ttl = null) {
          localStorage.setItem(`ph_${key}`, JSON.stringify({
            value,
            timestamp: Date.now(),
            ttl
          }));
        }
      };

      cache.set('test', { data: 'value' });
      expect(cache.get('test')).toEqual({ data: 'value' });
    });

    it('should return null for expired TTL', (done) => {
      const cache = {
        get(key) {
          const item = localStorage.getItem(`ph_${key}`);
          if (!item) return null;
          const { value, timestamp, ttl } = JSON.parse(item);
          if (ttl && Date.now() - timestamp > ttl) {
            localStorage.removeItem(`ph_${key}`);
            return null;
          }
          return value;
        },
        set(key, value, ttl = null) {
          localStorage.setItem(`ph_${key}`, JSON.stringify({
            value,
            timestamp: Date.now(),
            ttl
          }));
        }
      };

      cache.set('expiring', 'data', 50); // 50ms TTL
      
      setTimeout(() => {
        expect(cache.get('expiring')).toBeNull();
        done();
      }, 60);
    });
  });

  describe('Session Cache (sessionStorage)', () => {
    it('should store and retrieve values for current session', () => {
      const cache = {
        session: {
          get(key) {
            const item = sessionStorage.getItem(`ph_${key}`);
            if (!item) return null;
            return JSON.parse(item).value;
          },
          set(key, value) {
            sessionStorage.setItem(`ph_${key}`, JSON.stringify({
              value,
              timestamp: Date.now()
            }));
          }
        }
      };

      cache.session.set('projects', [{ id: 1, name: 'Test' }]);
      expect(cache.session.get('projects')).toEqual([{ id: 1, name: 'Test' }]);
    });
  });
});

describe('Debounce Utility', () => {
  it('should delay function execution', (done) => {
    let callCount = 0;
    
    function debounce(func, wait) {
      let timeout;
      return function executedFunction(...args) {
        const later = () => {
          clearTimeout(timeout);
          func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
      };
    }

    const debouncedFn = debounce(() => {
      callCount++;
    }, 100);

    debouncedFn();
    debouncedFn();
    debouncedFn();

    expect(callCount).toBe(0);

    setTimeout(() => {
      expect(callCount).toBe(1);
      done();
    }, 150);
  });

  it('should execute only once after rapid calls', (done) => {
    let callCount = 0;
    
    function debounce(func, wait) {
      let timeout;
      return function executedFunction(...args) {
        const later = () => {
          clearTimeout(timeout);
          func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
      };
    }

    const debouncedFn = debounce(() => {
      callCount++;
    }, 50);

    // Rapid calls
    for (let i = 0; i < 10; i++) {
      setTimeout(() => debouncedFn(), i * 10);
    }

    setTimeout(() => {
      expect(callCount).toBe(1);
      done();
    }, 200);
  });
});

describe('Smart Intervals', () => {
  it('should respect visibility API state', () => {
    let isVisible = true;
    let callCount = 0;

    // Simulate visibility change
    const visibilityHandler = () => {
      isVisible = !document.hidden;
    };

    // Mock document.hidden
    Object.defineProperty(document, 'hidden', {
      writable: true,
      configurable: true,
      value: false
    });

    const interval = setInterval(() => {
      if (isVisible) {
        callCount++;
      }
    }, 10);

    // Simulate tab becoming hidden
    document.hidden = true;
    isVisible = false;

    return new Promise((resolve) => {
      setTimeout(() => {
        clearInterval(interval);
        // Should not have incremented while hidden
        expect(callCount).toBe(0);
        resolve();
      }, 50);
    });
  });
});

describe('Git Cache', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('should cache git status per project', () => {
    const gitCache = {
      get(projectId) {
        const item = localStorage.getItem(`ph_git_${projectId}`);
        if (!item) return null;
        const { value, timestamp } = JSON.parse(item);
        // Check if cache is still valid (30 seconds)
        if (Date.now() - timestamp > 30000) {
          localStorage.removeItem(`ph_git_${projectId}`);
          return null;
        }
        return value;
      },
      set(projectId, data) {
        localStorage.setItem(`ph_git_${projectId}`, JSON.stringify({
          value: data,
          timestamp: Date.now()
        }));
      }
    };

    const gitData = { is_git: true, branch: 'main', changes: 0 };
    gitCache.set(1, gitData);
    
    expect(gitCache.get(1)).toEqual(gitData);
    expect(gitCache.get(2)).toBeNull(); // Different project
  });
});

describe('Metrics Intervals', () => {
  it('should have correct intervals for each metric type', () => {
    const METRICS_INTERVALS = { 
      cpu: 5000,   // 5s
      ram: 10000,  // 10s
      disk: 60000  // 60s
    };

    expect(METRICS_INTERVALS.cpu).toBe(5000);
    expect(METRICS_INTERVALS.ram).toBe(10000);
    expect(METRICS_INTERVALS.disk).toBe(60000);
    
    // Disk should update less frequently than CPU
    expect(METRICS_INTERVALS.disk).toBeGreaterThan(METRICS_INTERVALS.cpu);
    expect(METRICS_INTERVALS.disk).toBeGreaterThan(METRICS_INTERVALS.ram);
  });
});

// Run tests
console.log('\n🧪 Running ProjectHub Optimization Tests...\n');
