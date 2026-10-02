variable "location" {
  type        = string
  description = "Azure region for every resource in this environment."
  default     = "eastasia"
}

variable "resource_group_name" {
  type        = string
  description = "Resource group holding the observability resources."
}

variable "log_analytics_name" {
  type        = string
  description = "Log Analytics workspace name. Globally unique, 3-63 lowercase letters/digits/hyphens."
}

variable "application_insights_name" {
  type        = string
  description = "Application Insights component name. Globally unique."
}

variable "sku_name" {
  type        = string
  description = "Log Analytics SKU. Bicep parity used PerGB2018."
  default     = "PerGB2018"
}

variable "retention_days" {
  type        = number
  description = "Log retention in days. 30 matches Bicep parity. Below 30 the forensic window for a data incident is too short to be useful; above it, cost grows linearly for no operational gain at this scale."
  default     = 30
}

variable "daily_quota_gb" {
  type        = number
  description = "Daily ingestion cap in GB. A cap is a cost control, not a performance setting: without it an unexpected telemetry burst bills without limit. -1 means uncapped, which is never appropriate outside the validation environment."
  default     = 5
}

variable "alert_rules" {
  type = map(object({
    display_name = string
    description  = string
    severity     = number
    metric       = string
    threshold    = number
    operator     = string
    window       = string
    frequency    = string
  }))
  description = "Azure Monitor metric alert rules. A map keyed by a stable id so a rename is a diff, not a delete+create. Each rule exists because a specific operational failure it is responsible for is named in the description — an alert nobody can act on is a notification, not a control."
  default     = {}
}

variable "action_group_name" {
  type        = string
  description = "Name of the Monitor action group every alert routes to. Null means alerts are created without a notification target, which is a deliberate validation-environment choice and must never be the prod state."
  default     = null
}

variable "alert_email" {
  type        = string
  description = "Email that receives alert notifications. This is the only human route back from a page, so it must be a monitored mailbox. Null skips the action group entirely, which is the honest dev/validation state: the rules exist and nothing pages anyone."
  default     = null
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to every observability resource."
  default     = {}
}
