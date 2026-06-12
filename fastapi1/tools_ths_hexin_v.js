const fs = require("fs");
const https = require("https");
const vm = require("vm");

const scriptPath = process.argv[2] || "chameleon.js";
const targetUrl = process.argv[3] || "https://q.10jqka.com.cn/";
const userAgent = process.argv[4] || "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36";

const cookieJar = {};

function setCookie(value) {
  const first = String(value).split(";")[0];
  const eq = first.indexOf("=");
  if (eq > 0) {
    cookieJar[first.slice(0, eq).trim()] = first.slice(eq + 1);
  }
}

function getCookie() {
  return Object.entries(cookieJar).map(([k, v]) => `${k}=${v}`).join("; ");
}

const locationUrl = new URL(targetUrl);

const document = {
  body: {
    appendChild() {},
    removeChild() {},
  },
  head: {
    appendChild(node) {
      if (typeof node.onload === "function") {
        setTimeout(() => node.onload(), 0);
      }
    },
    insertBefore(node) {
      if (typeof node.onload === "function") {
        setTimeout(() => node.onload(), 0);
      }
    },
  },
  documentElement: {
    addBehavior() {},
  },
  createElement(tagName) {
    const node = {
      tagName: String(tagName).toUpperCase(),
      style: {},
      children: [],
      appendChild(child) {
        this.children.push(child);
      },
      setAttribute(name, value) {
        this[name] = value;
      },
      getAttribute(name) {
        return this[name];
      },
      addBehavior() {},
      load() {},
      save() {},
      getContext() {
        return {
          fillText() {},
          measureText() { return { width: 1 }; },
          getImageData() { return { data: [0, 0, 0, 0] }; },
        };
      },
    };
    return node;
  },
  getElementsByTagName(name) {
    if (String(name).toLowerCase() === "head") return [this.head];
    if (String(name).toLowerCase() === "body") return [this.body];
    return [this.createElement(name)];
  },
  addEventListener() {},
  attachEvent() {},
};

Object.defineProperty(document, "cookie", {
  get: getCookie,
  set: setCookie,
});

const localStorageMap = new Map();
const localStorage = {
  getItem(key) { return localStorageMap.has(key) ? localStorageMap.get(key) : null; },
  setItem(key, value) { localStorageMap.set(key, String(value)); },
  removeItem(key) { localStorageMap.delete(key); },
};

function XMLHttpRequest() {}
XMLHttpRequest.prototype.open = function () {};
XMLHttpRequest.prototype.send = function () {};
XMLHttpRequest.prototype.setRequestHeader = function (name, value) {
  if (String(name).toLowerCase() === "hexin-v") {
    cookieJar["hexin-v"] = value;
  }
};
XMLHttpRequest.prototype.getAllResponseHeaders = function () { return ""; };

const window = {
  document,
  navigator: null,
  location: {
    href: targetUrl,
    protocol: locationUrl.protocol,
    host: locationUrl.host,
    hostname: locationUrl.hostname,
    pathname: locationUrl.pathname,
    search: locationUrl.search,
  },
  localStorage,
  XMLHttpRequest,
  addEventListener() {},
  attachEvent() {},
  setInterval,
  clearInterval,
  setTimeout,
  clearTimeout,
  Math,
  Date,
  RegExp,
  Array,
  String,
  Number,
  Object,
  Function,
  Map,
  WeakMap,
  encodeURIComponent,
};

const navigator = {
  userAgent,
  appVersion: userAgent,
  platform: "Win32",
  language: "zh-CN",
  languages: ["zh-CN", "zh"],
  vendor: "Google Inc.",
  plugins: [{ name: "Chrome PDF Plugin" }],
  javaEnabled() { return false; },
};
window.navigator = navigator;

const context = vm.createContext({
  window,
  document,
  navigator,
  location: window.location,
  localStorage,
  XMLHttpRequest,
  Headers: class Headers {
    constructor() { this.map = {}; }
    append(k, v) { this.map[k] = v; }
  },
  Request: class Request {},
  Element: function Element() {},
  ActiveXObject: undefined,
  TOKEN_SERVER_TIME: undefined,
  setInterval,
  clearInterval,
  setTimeout,
  clearTimeout,
  Math,
  Date,
  RegExp,
  Array,
  String,
  Number,
  Object,
  Function,
  Map,
  WeakMap,
  encodeURIComponent,
  console: { log() {}, error() {} },
});

function download(url) {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      let data = "";
      res.setEncoding("utf8");
      res.on("data", chunk => data += chunk);
      res.on("end", () => resolve(data));
    }).on("error", reject);
  });
}

async function readChameleon() {
  if (fs.existsSync(scriptPath)) {
    return fs.readFileSync(scriptPath, "utf8");
  }
  return await download("https://s.thsi.cn/js/chameleon/chameleon.1.7.min.1780607.js");
}

(async () => {
  const code = await readChameleon();
  vm.runInContext(code, context, { timeout: 5000 });

  const result = {
    cookie: getCookie(),
    hexinV: cookieJar["v"] || cookieJar["hexin-v"] || localStorage.getItem("v") || localStorage.getItem("hexin-v") || null,
    keys: Object.keys(cookieJar),
  };

  console.log(JSON.stringify(result));
  process.exit(0);
})().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
