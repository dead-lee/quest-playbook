package com.shop.oms.common;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.Map;

import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

/** Small JSON-over-HTTP helper used for service-to-service calls. */
public final class Http {

    private Http() {
    }

    public static RestClient client(String baseUrl) {
        HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5))
                .version(HttpClient.Version.HTTP_1_1).build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(http);
        factory.setReadTimeout(Duration.ofSeconds(60));
        return RestClient.builder().baseUrl(baseUrl).requestFactory(factory).build();
    }

    @SuppressWarnings("unchecked")
    public static <T> T post(RestClient client, String path, Object body, Class<T> type) {
        try {
            return client.post().uri(path).body(body == null ? Map.of() : body).retrieve().body(type);
        } catch (RestClientResponseException e) {
            Map<String, Object> err = null;
            try {
                err = e.getResponseBodyAs(Map.class);
            } catch (RuntimeException ignored) {
                // body was not JSON
            }
            int code = err != null && err.get("mysqlError") instanceof Number n ? n.intValue() : 0;
            throw new RemoteCallException(path + " -> " + e.getStatusCode().value() + " " + err,
                    e.getStatusCode().value(), code);
        }
    }
}
