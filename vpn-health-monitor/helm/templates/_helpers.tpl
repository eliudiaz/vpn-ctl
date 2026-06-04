{{/*
Expand the name of the chart.
*/}}
{{- define "vpn-health-monitor.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "vpn-health-monitor.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "vpn-health-monitor.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "vpn-health-monitor.labels" -}}
helm.sh/chart: {{ include "vpn-health-monitor.chart" . }}
{{ include "vpn-health-monitor.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "vpn-health-monitor.selectorLabels" -}}
app.kubernetes.io/name: {{ include "vpn-health-monitor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app: vpn-health-monitor
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "vpn-health-monitor.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "vpn-health-monitor.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
