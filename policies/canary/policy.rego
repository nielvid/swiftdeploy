package canary

import rego.v1

default allow := false

allow if {
    count(deny) == 0
}

deny contains msg if {
    input.error_rate > data.canary.max_error_rate
    msg := sprintf(
        "Error rate %v%% exceeds maximum %v%%",
        [round(input.error_rate * 100), round(data.canary.max_error_rate * 100)]
    )
}

deny contains msg if {
    input.p99_ms > data.canary.max_p99_ms
    msg := sprintf(
        "P99 latency %vms exceeds maximum %vms",
        [input.p99_ms, data.canary.max_p99_ms]
    )
}
