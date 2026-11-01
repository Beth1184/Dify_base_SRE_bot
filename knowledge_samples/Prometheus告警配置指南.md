# Prometheus 告警规则配置指南

## 适用场景
需要在 Prometheus 中新增或调整告警规则时使用本指南。

## 告警规则存放位置
- 规则文件目录：`/etc/prometheus/rules/`
- 规则文件命名：`<服务名>.yml`

## 配置示例
```yaml
groups:
  - name: service_cpu
    rules:
      - alert: cpu_usage_high
        expr: 100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "{{ $labels.instance }} CPU 使用率过高"
```

## 阈值建议
| 指标 | warning | critical | 持续时间 |
|------|---------|----------|---------|
| CPU 使用率 | > 80% | > 90% | 5m |
| 内存使用率 | > 85% | > 95% | 5m |
| 磁盘使用率 | > 85% | > 92% | 10m |

## 变更流程
1. 修改规则文件
2. 执行 `promtool check rules <文件>` 校验语法
3. 提交变更审批
4. 重载 Prometheus 配置

## 联系人
监控平台负责人：@监控值班
