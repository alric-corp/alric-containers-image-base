package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
)

func request(t *testing.T, method, path string) *httptest.ResponseRecorder {
	t.Helper()
	recorder := httptest.NewRecorder()
	newHandler().ServeHTTP(recorder, httptest.NewRequest(method, path, nil))
	return recorder
}

func TestHealthIsOK(t *testing.T) {
	response := request(t, http.MethodGet, "/health")
	if response.Code != http.StatusOK {
		t.Fatalf("status %d", response.Code)
	}
	var body map[string]string
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil || body["status"] != "ok" {
		t.Fatalf("body %q (%v)", response.Body.String(), err)
	}
}

func TestInfoReportsTheProcessIdentity(t *testing.T) {
	response := request(t, http.MethodGet, "/info")
	var body struct {
		Status   string         `json:"status"`
		Security map[string]int `json:"security"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body.Status != "ok" || body.Security["uid"] != os.Getuid() || body.Security["gid"] != os.Getgid() {
		t.Fatalf("info %+v", body)
	}
}

func TestOnlyDeclaredRoutesAndMethodsAnswer(t *testing.T) {
	if code := request(t, http.MethodPost, "/health").Code; code != http.StatusMethodNotAllowed {
		t.Fatalf("POST /health: %d", code)
	}
	if code := request(t, http.MethodGet, "/missing").Code; code != http.StatusNotFound {
		t.Fatalf("GET /missing: %d", code)
	}
}
