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

# Enabled through google.api_bootstrap so the Service Usage call is billed to
# the caller, not to the target project whose Service Usage API is still off.
# Any of the three projects this root touches can be fresh, so all are covered.
resource "google_project_service" "bootstrap" {
  provider = google.api_bootstrap
  for_each = {
    for pair in setproduct(toset(local.all_project_ids), local.bootstrap_services) :
    "${pair[0]}_${replace(pair[1], ".", "_")}" => {
      project = pair[0]
      service = pair[1]
    }
  }

  project            = each.value.project
  service            = each.value.service
  disable_on_destroy = false
}

# for_each, not count, so adding or removing an API does not renumber the rest.
resource "google_project_service" "cicd_services" {
  for_each = toset(local.cicd_services)

  project            = var.cicd_runner_project_id
  service            = each.value
  disable_on_destroy = false

  depends_on = [google_project_service.bootstrap]
}

resource "google_project_service" "deploy_project_services" {
  for_each = {
    for pair in setproduct(keys(local.deploy_project_ids), local.deploy_project_services) :
    "${pair[0]}_${replace(pair[1], ".", "_")}" => {
      project = local.deploy_project_ids[pair[0]]
      service = pair[1]
    }
  }
  project            = each.value.project
  service            = each.value.service
  disable_on_destroy = false

  depends_on = [google_project_service.bootstrap]
}
