const _listeners = {};

export const EventEmitter = {
  on(event, fn) {
    if (!_listeners[event]) _listeners[event] = new Set();
    _listeners[event].add(fn);
    return () => _listeners[event]?.delete(fn);
  },
  emit(event, data) {
    _listeners[event]?.forEach(fn => fn(data));
  },
};
