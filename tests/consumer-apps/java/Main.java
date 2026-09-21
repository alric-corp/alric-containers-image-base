import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

// A downstream web service built entirely with the JDK, without Maven/Gradle.
public final class Main {
    private static boolean writable(String directory) {
        Path file = null;
        try {
            file = Files.createTempFile(Path.of(directory), "consumer-write-", ".txt");
            Files.writeString(file, "consumer-app");
            boolean valid = Files.readString(file).equals("consumer-app");
            Files.delete(file);
            file = null;
            return valid;
        } catch (IOException error) {
            return false;
        } finally {
            if (file != null) {
                try { Files.deleteIfExists(file); } catch (IOException ignored) { }
            }
        }
    }

    private static Map<String, Object> security() throws IOException {
        Map<String, String> fields = new HashMap<>();
        for (String line : Files.readAllLines(Path.of("/proc/self/status"))) {
            String[] parts = line.split(":", 2);
            if (parts.length == 2) fields.put(parts[0], parts[1].trim());
        }
        boolean readonly = false;
        String rootError = "write unexpectedly succeeded";
        Path probe = Path.of("/app/certification-root-probe");
        try {
            Files.writeString(probe, "must fail on read-only root");
            Files.delete(probe);
        } catch (IOException error) {
            rootError = error.getMessage();
            readonly = error instanceof java.nio.file.FileSystemException
                && "Read-only file system".equals(((java.nio.file.FileSystemException) error).getReason());
        }
        Map<String, Object> result = new HashMap<>();
        result.put("uid", Integer.parseInt(fields.get("Uid").split("\\s+")[1]));
        result.put("gid", Integer.parseInt(fields.get("Gid").split("\\s+")[1]));
        result.put("read_only_root", readonly);
        result.put("root_write_error", rootError);
        result.put("writable_tmp", writable("/tmp"));
        result.put("writable_app_work", writable("/app/work"));
        result.put("cap_eff", fields.get("CapEff"));
        result.put("no_new_privileges", "1".equals(fields.get("NoNewPrivs")));
        return result;
    }

    private static String quote(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (char ch : value.toCharArray()) {
            if (ch == '"' || ch == '\\') out.append('\\').append(ch);
            else if (ch < 0x20) out.append(String.format("\\u%04x", (int) ch));
            else out.append(ch);
        }
        return out.append('"').toString();
    }

    private static String json(Object value) {
        if (value instanceof Map<?, ?> values) {
            StringBuilder out = new StringBuilder("{");
            String separator = "";
            for (var entry : values.entrySet()) {
                out.append(separator).append(quote(entry.getKey().toString()))
                    .append(':').append(json(entry.getValue()));
                separator = ",";
            }
            return out.append('}').toString();
        }
        if (value instanceof Boolean || value instanceof Number) return value.toString();
        if (value == null) return "null";
        return quote(value.toString());
    }

    private static void handle(HttpExchange exchange) throws IOException {
        int status = 200;
        Map<String, Object> body;
        try {
            if (!exchange.getRequestMethod().equals("GET")) {
                status = 405;
                body = Map.of("status", "method_not_allowed");
            } else {
                body = switch (exchange.getRequestURI().getPath()) {
                    case "/health", "/ready" -> Map.of("status", "ok");
                    case "/info" -> {
                        String arch = System.getProperty("os.arch");
                        if (arch.equals("x86_64")) arch = "amd64";
                        if (arch.equals("aarch64")) arch = "arm64";
                        yield Map.of("status", "ok", "runtime", "java",
                            "runtime_version", Runtime.version().toString(),
                            "architecture", arch, "security", security());
                    }
                    default -> { status = 404; yield Map.of("status", "not_found"); }
                };
            }
        } catch (Exception error) {
            status = 500;
            body = Map.of("status", "error", "error", error.toString());
        }
        byte[] bytes = json(body).getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, bytes.length);
        try (var response = exchange.getResponseBody()) { response.write(bytes); }
    }

    public static void main(String[] args) throws Exception {
        var server = HttpServer.create(new InetSocketAddress("0.0.0.0", 8080), 0);
        var executor = Executors.newCachedThreadPool();
        var stopped = new CountDownLatch(1);
        server.setExecutor(executor);
        server.createContext("/", Main::handle);
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            server.stop(1);
            executor.shutdown();
            try {
                if (!executor.awaitTermination(3, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                    throw new IllegalStateException("HTTP workers did not stop gracefully");
                }
                // JVM SIGTERM normally exits 143 even when this hook completes.
                System.out.println("consumer shutdown complete");
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            } finally {
                stopped.countDown();
            }
        }, "consumer-shutdown"));
        server.start();
        stopped.await();
    }
}
