/**
 * Format a date object into YYYY-MM-DD string.
 */
function formatDate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

async function fetchUserData(userId) {
    const response = await fetch(`/api/users/${userId}`);
    return response.json();
}

const slugify = (text) => {
    return text.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
};

class EventEmitter {
    constructor() {
        this.listeners = {};
    }

    on(event, callback) {
        if (!this.listeners[event]) {
            this.listeners[event] = [];
        }
        this.listeners[event].push(callback);
    }

    emit(event, ...args) {
        const handlers = this.listeners[event] || [];
        handlers.forEach(fn => fn(...args));
    }

    off(event, callback) {
        if (!this.listeners[event]) return;
        this.listeners[event] = this.listeners[event].filter(fn => fn !== callback);
    }
}

export default function createEmitter() {
    return new EventEmitter();
}
