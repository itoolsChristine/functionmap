interface Config {
    host: string;
    port: number;
    debug: boolean;
}

type LogLevel = 'info' | 'warn' | 'error';

function clamp(value: number, min: number, max: number): number {
    return Math.min(Math.max(value, min), max);
}

async function loadConfig(path: string): Promise<Config> {
    const raw = await import(path);
    return raw.default as Config;
}

const debounce = (fn: (...args: unknown[]) => void, ms: number): ((...args: unknown[]) => void) => {
    let timer: ReturnType<typeof setTimeout>;
    return (...args: unknown[]) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), ms);
    };
};

class Logger {
    private level: LogLevel;

    constructor(level: LogLevel = 'info') {
        this.level = level;
    }

    log(message: string): void {
        console.log(`[${this.level}] ${message}`);
    }

    setLevel(level: LogLevel): void {
        this.level = level;
    }

    static create(level: LogLevel): Logger {
        return new Logger(level);
    }
}

export function getDefaultLogger(): Logger {
    return Logger.create('info');
}
