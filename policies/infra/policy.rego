package infra

import rego.v1

default allow := false

allow if {
    count(deny) == 0
}

deny contains msg if {
    input.disk_free_gb < data.infra.min_disk_gb
    msg := sprintf(
        "Disk free %vGB is below minimum %vGB",
        [input.disk_free_gb, data.infra.min_disk_gb]
    )
}

deny contains msg if {
    input.cpu_load > data.infra.max_cpu_load
    msg := sprintf(
        "CPU load %v exceeds maximum %v",
        [input.cpu_load, data.infra.max_cpu_load]
    )
}
