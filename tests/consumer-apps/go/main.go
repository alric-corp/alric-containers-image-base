// A downstream HTTP application: its only dependency is the Go standard library.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"runtime"
	"strings"
	"syscall"
	"time"
)

func writable(directory string) bool {
	f, err := os.CreateTemp(directory, "consumer-write-*")
	if err != nil {
		return false
	}
	defer os.Remove(f.Name())
	_, writeErr := f.WriteString("consumer-app")
	closeErr := f.Close()
	data, readErr := os.ReadFile(f.Name())
	removeErr := os.Remove(f.Name())
	return writeErr == nil && closeErr == nil && readErr == nil && removeErr == nil && string(data) == "consumer-app"
}

func security() map[string]any {
	fields := map[string]string{}
	status, err := os.ReadFile("/proc/self/status")
	if err == nil {
		for _, line := range strings.Split(string(status), "\n") {
			parts := strings.SplitN(line, ":", 2)
			if len(parts) == 2 {
				fields[parts[0]] = strings.TrimSpace(parts[1])
			}
		}
	}
	path := "/app/certification-root-probe"
	writeErr := os.WriteFile(path, []byte("must fail on read-only root"), 0600)
	if writeErr == nil {
		_ = os.Remove(path)
	}
	message := "write unexpectedly succeeded"
	if writeErr != nil {
		message = writeErr.Error()
	}
	return map[string]any{
		"uid": os.Getuid(), "gid": os.Getgid(),
		"read_only_root": errors.Is(writeErr, syscall.EROFS), "root_write_error": message,
		"writable_tmp": writable("/tmp"), "writable_app_work": writable("/app/work"),
		"cap_eff": fields["CapEff"], "no_new_privileges": fields["NoNewPrivs"] == "1",
	}
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.Method != http.MethodGet {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		var body any
		switch r.URL.Path {
		case "/health", "/ready":
			body = map[string]string{"status": "ok"}
		case "/info":
			body = map[string]any{
				"status": "ok", "runtime": "go", "runtime_version": runtime.Version(),
				"architecture": runtime.GOARCH, "security": security(),
			}
		default:
			w.WriteHeader(http.StatusNotFound)
			body = map[string]string{"status": "not_found"}
		}
		_ = json.NewEncoder(w).Encode(body)
	})
	server := &http.Server{Addr: ":8080", Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()
	errorsCh := make(chan error, 1)
	go func() { errorsCh <- server.ListenAndServe() }()
	select {
	case err := <-errorsCh:
		log.Fatal(err)
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := server.Shutdown(shutdownCtx); err != nil {
			log.Fatal(err)
		}
		fmt.Println("consumer shutdown complete")
	}
}
