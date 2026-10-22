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

# Data source to get project numbers.
# depends_on defers the read to apply time, after bootstrap has enabled Cloud
# Resource Manager.
data "google_project" "projects" {
  for_each   = local.deploy_project_ids
  project_id = each.value

  depends_on = [google_project_service.bootstrap]
}

# 1. Assign roles for the CICD project
resource "google_project_iam_member" "cicd_project_roles" {
  for_each = toset(var.cicd_roles)

  project    = var.cicd_runner_project_id
  role       = each.value
  member     = "serviceAccount:${resource.google_service_account.cicd_runner_sa.email}"
  depends_on = [resource.google_project_service.cicd_services, resource.google_project_service.deploy_project_services]

}

# 2. Assign roles for the other two projects (prod and staging)
resource "google_project_iam_member" "other_projects_roles" {
  for_each = {
    for pair in setproduct(keys(local.deploy_project_ids), var.cicd_sa_deployment_required_roles) :
    "${pair[0]}-${pair[1]}" => {
      project_id = local.deploy_project_ids[pair[0]]
      role       = pair[1]
    }
  }

  project    = each.value.project_id
  role       = each.value.role
  member     = "serviceAccount:${resource.google_service_account.cicd_runner_sa.email}"
  depends_on = [resource.google_project_service.cicd_services, resource.google_project_service.deploy_project_services]
}
# 3. Grant the Agent Identity principal the permissions required to run the application.
resource "google_project_iam_member" "agent_identity_roles" {
  for_each = {
    for pair in setproduct(keys(local.deploy_project_ids), var.agent_identity_roles) :
    join(",", pair) => {
      engine_key = pair[0]
      project    = local.deploy_project_ids[pair[0]]
      role       = pair[1]
    }
  }

  project = each.value.project
  role    = each.value.role
  member  = "principal://${google_vertex_ai_reasoning_engine.app[each.value.engine_key].spec[0].effective_identity}"
}

resource "google_storage_bucket_iam_member" "agent_identity_logs_bucket" {
  for_each = local.deploy_project_ids

  bucket = google_storage_bucket.logs_data_bucket[each.value].name
  role   = "roles/storage.objectAdmin"
  member = "principal://${google_vertex_ai_reasoning_engine.app[each.key].spec[0].effective_identity}"
}





# Special assignment: Allow the CICD SA to create tokens
resource "google_service_account_iam_member" "cicd_run_invoker_token_creator" {
  service_account_id = google_service_account.cicd_runner_sa.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${resource.google_service_account.cicd_runner_sa.email}"
  depends_on         = [resource.google_project_service.cicd_services, resource.google_project_service.deploy_project_services]
}
# Special assignment: Allow the CICD SA to impersonate itself for trigger creation
resource "google_service_account_iam_member" "cicd_run_invoker_account_user" {
  service_account_id = google_service_account.cicd_runner_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${resource.google_service_account.cicd_runner_sa.email}"
  depends_on         = [resource.google_project_service.cicd_services, resource.google_project_service.deploy_project_services]
}
