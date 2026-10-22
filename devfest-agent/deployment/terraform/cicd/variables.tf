# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

variable "project_name" {
  type        = string
  description = "Project name used as a base for resource naming"
  default     = "devfest-agent"
}

variable "prod_project_id" {
  type        = string
  description = "**Production** Google Cloud Project ID for resource deployment."
}

variable "staging_project_id" {
  type        = string
  description = "**Staging** Google Cloud Project ID for resource deployment."
}

variable "cicd_runner_project_id" {
  type        = string
  description = "Google Cloud Project ID where CI/CD pipelines will execute."
}

variable "region" {
  type        = string
  description = "Google Cloud region for resource deployment."
  default     = "us-east1"
}

variable "host_connection_name" {
  description = "Name of the host connection to create in Cloud Build"
  type        = string
  default     = "devfest-agent-github-connection"
}

variable "repository_name" {
  description = "Name of the repository you'd like to connect to Cloud Build"
  type        = string
}

variable "app_sa_roles" {
  description = "List of roles to assign to the application service account"
  type        = list(string)
  default = [

    "roles/aiplatform.user",
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
    "roles/storage.admin",
    "roles/serviceusage.serviceUsageConsumer",
  ]
}

variable "cicd_roles" {
  description = "List of roles to assign to the CICD runner service account in the CICD project"
  type        = list(string)
  default = [
    "roles/storage.admin",
    "roles/aiplatform.user",
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
    "roles/artifactregistry.writer",
    "roles/cloudbuild.builds.builder"
  ]
}

variable "cicd_sa_deployment_required_roles" {
  description = "List of roles to assign to the CICD runner service account for the Staging and Prod projects."
  type        = list(string)
  default = [
    "roles/iam.serviceAccountUser",
    "roles/aiplatform.user",
    "roles/storage.admin"
  ]
}

variable "repository_owner" {
  description = "Owner of the Git repository - username or organization"
  type        = string
}




variable "create_repository" {
  description = "Flag indicating whether to create a new Git repository"
  type        = bool
  default     = false
}


variable "agent_framework" {
  description = "Framework label on the Agent Runtime deployment. The Google Cloud console reads it to pick a playground; override it when the container is not an ADK app."
  type        = string
  default     = "google-adk"
}

variable "agent_identity_roles" {
  description = "List of roles to assign to each agent's Agent Identity principal. Keep the first six in sync with AGENT_IDENTITY_ROLES in agents-cli, which `agents-cli deploy` grants."
  type        = list(string)
  default = [
    "roles/aiplatform.user",
    "roles/serviceusage.serviceUsageConsumer",
    "roles/browser",
    "roles/cloudapiregistry.viewer",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/cloudtrace.agent",
  ]
}
