import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8080/v1";
const TOKEN = __ENV.TOKEN || "";
const SCENARIO = __ENV.SCENARIO || "board";

export const options = {
  vus: Number(__ENV.VUS || 10),
  duration: __ENV.DURATION || "2m",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: SCENARIO === "search" ? ["p(95)<500"] : ["p(95)<1500"],
  },
};

function authHeaders() {
  const headers = { Accept: "application/json" };
  if (TOKEN) {
    headers.Authorization = `Bearer ${TOKEN}`;
  }
  return headers;
}

export default function () {
  if (SCENARIO === "search") {
    const res = http.get(`${BASE_URL}/assets/search?q=jersey&limit=20`, {
      headers: authHeaders(),
    });
    check(res, {
      "search status 200": (r) => r.status === 200,
    });
  } else {
    const res = http.get(`${BASE_URL}/board?limit=100`, {
      headers: authHeaders(),
    });
    check(res, {
      "board status 200": (r) => r.status === 200,
    });
  }
  sleep(1);
}
