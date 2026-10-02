# EDGE TIER — Front Door Premium + WAF + APIM
#
# SCOPE: this module exists so the edge can be *reviewed* before it is *billed*.
# It is not instantiated by default (see enable_edge in the root). A module that
# is written but never enabled is the honest form of "we know what the edge
# requires" — as opposed to a diagram implying a deployed edge.
#
# WHY APIM IS NOT FREE OF CERTAINTY HERE
# Factory's API authenticates with a shared API key compared inside the app
# (app/api/security.py). APIM adds rate limiting and a subscription key layer in
# front of that, which is genuinely useful, but it is also a second credential
# store and a second thing to rotate. The module therefore does NOT assume APIM
# is the right answer; it makes the option concrete and leaves enable_edge=false
# until Phase 8 proves the need.
#
# The WAF policy is `Prevention`, not `Detection`: a WAF in detection mode logs
# attacks and blocks nothing, which is the single most common way a WAF
# deployment produces a false sense of security.

variable "location" {
  type        = string
  description = "Azure region for region-bound edge resources. Front Door and APIM are global; the resource group is still region-tagged for consistency."
  default     = "eastasia"
}

variable "resource_group_name" {
  type        = string
  description = "Resource group holding the edge resources."
}

variable "origin_hostname" {
  type        = string
  description = "Backend hostname the edge fronts, typically the Container App FQDN."
}

variable "waf_mode" {
  type        = string
  description = "WAF mode. Prevention is the only acceptable production value; Detection is permitted in the validation environment to measure false positives before enforcing."
  default     = "Prevention"

  validation {
    condition     = contains(["Prevention", "Detection"], var.waf_mode)
    error_message = "waf_mode must be Prevention or Detection."
  }
}


variable "publisher_email" {
  type        = string
  description = "Publisher contact email for the API Management service, shown in the developer portal and used by Azure for service notices. Must be a monitored mailbox."
  default     = "binhtan5734@gmail.com"
}

variable "rate_limit_per_minute" {
  type        = number
  description = "APIM rate limit per client, per minute. Set from a measured baseline, not a guess; a limit below normal traffic causes an outage, and one above it protects nothing."
  default     = 120
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to every edge resource."
  default     = {}
}
