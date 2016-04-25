#!/usr/bin/python
#
# Copyright (c) 2016 Matt Davis, <mdavis@ansible.com>
#                    Chris Houseknecht, <house@redhat.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#

DOCUMENTATION = '''
---
module: azure_rm_storageblob

short_description: Manage blob containers and blob objects.

version_added: "2.1"

description:
    - Create, update and delete blob containers and blob objects. Use to upload a file and store it as a blob object,
      or download a blob object to a file.

options:
    storage_account_name:
        description:
            - Name of the storage account to use.
        required: true
        aliases:
            - account_name
    blob:
        description:
            - Name of a blob object within the container.
        required: false
        default: null
        aliases:
            - blob_name
    container:
        description:
            - Name of a blob container within the storage account.
        required: true
        aliases:
            - container_name
    content_type:
        description:
            - Set the blob content-type header. For example, 'image/png'.
        default: null
        required: false
    cache_control:
        description:
            - Set the blob cache-control header.
        required: false
        default: null
    content_disposition:
        description:
            - Set the blob content-disposition header.
        required: false
        default: null
    content_encoding:
        description:
            - Set the blob encoding header.
        required: false
        default: null
    content_language:
        description:
            - Set the blob content-language header.
        required: false
        default: null
    content_md5:
        description:
            - Set the blob md5 hash value.
        required: false
        default: null
    dest:
        description:
            - Destination file path. Use with state 'present' to download a blob.
        aliases:
            - destination
        required: false
        default: null
    force:
        description:
            - Overwrite existing blob or file when uploading or downloading. Force deletion of a container
              that contains blobs.
        default: false
        required: false
    resource_group:
        description:
            - Name of the resource group to use.
        required: true
    src:
        description:
            - Source file path. Use with state 'present' to upload a blob.
        aliases:
            - source
        required: false
        default: null
    state:
        description:
            - Assert the state of a container or blob.
            - Use state 'absent' with a container value only to delete a container. Include a blob value to remove
              a specific blob. A container will not be deleted, if it contains blobs. Use the force option to override,
              deleting the container and all associated blobs.
            - Use state 'present' to create or update a container and upload or download a blob. If the container
              does not exist, it will be created. If it exists, it will be updated with configuration options. Provide
              a blob name and either src or dest to upload or download. Provide a src path to upload and a dest path
              to download. If a blob (uploading) or a file (downloading) already exists, it will not be overwritten
              unless the force parameter is true.
        default: present
        required: false
        choices:
            - absent
            - present
    public_access:
        description:
            - Determine a container's level of public access. By default containers are private. Can only be set at
              time of container creation.
        required: false
        default: null
        choices:
            - container
            - blob
    tags:
        description:
            - "Dictionary of string:string pairs to assign as metadata to the object. Metadata tags on the object
              will be updated with any provided values. To remove tags use the purge_tags option."
        required: false
        default: null
    purge_tags:
        description:
            - Use to remove tags from an object. Any tags not found in the tags parameter will be removed from
              the object's metadata.
        required: false
        default: false

extends_documentation_fragment:
    - azure

author:
    - "Chris Houseknecht (@chouseknecht)"
    - "Matt Davis (@nitzmahone)"

'''

EXAMPLES = '''
- name: Remove container foo
  azure_rm_storageblob:
    resource_group: testing
    storage_account_name: clh0002
    container: foo
    state: absent

- name: Create container foo and upload a file
  azure_rm_storageblob:
    resource_group: Testing
    storage_account_name: clh0002
    container: foo
    blob: graylog.png
    src: ./files/graylog.png
    public_access: container
    content_type: 'application/image'

- name: Download the file
  azure_rm_storageblob:
    resource_group: Testing
    storage_account_name: clh0002
    container: foo
    blob: graylog.png
    dest: ~/tmp/images/graylog.png
'''

RETURN = '''
changed:
    description: Whether or not the object was changed.
    returned: always
    type: bool
    sample: True
actions:
    description: List of descriptive actions taken by the module.
    returned: always
    type: list
    sample: [
        "updated blob foo:graylog.png content settings."
    ]
blob:
    description: Facts about the current state of the blob.
    returned: when a blob is operated on
    type: dict
    sample: {
        "content_length": 136532,
        "content_settings": {
            "cache_control": null,
            "content_disposition": null,
            "content_encoding": null,
            "content_language": null,
            "content_md5": null,
            "content_type": "application/image"
        },
        "last_modified": "09-Mar-2016 22:08:25 +0000",
        "name": "graylog.png",
        "tags": {},
        "type": "BlockBlob"
    }
container:
    description: Facts about the current state of the selcted container.
    returned: always
    type: dict
    sample: {
        "last_mdoified": "09-Mar-2016 19:28:26 +0000",
        "name": "foo",
        "tags": {}
    }
'''


import datetime
import hashlib
import os

from ansible.module_utils.basic import *
from ansible.module_utils.azure_rm_common import *


try:
    from azure.storage.blob.models import ContentSettings
    from azure.storage.cloudstorageaccount import CloudStorageAccount
    from azure.common import AzureMissingResourceHttpError, AzureHttpError
except ImportError:
    # This is handled in azure_rm_common
    pass


NAME_PATTERN = re.compile(r"^(?!-)(?!.*--)[a-z0-9\-]+$")


class AzureRMStorageBlob(AzureRMModuleBase):

    def __init__(self):

        self.module_arg_spec = dict(
            storage_account_name=dict(required=True, type='str', aliases=['account_name']),
            blob=dict(type='str', aliases=['blob_name']),
            container=dict(required=True, type='str', aliases=['container_name']),
            dest=dict(type='str'),
            force=dict(type='bool', default=False),
            resource_group=dict(required=True, type='str'),
            src=dict(type='str'),
            state=dict(type='str', default='present', choices=['absent', 'present']),
            public_access=dict(type='str', choices=['container', 'blob']),
            content_type=dict(type='str'),
            content_encoding=dict(type='str'),
            content_language=dict(type='str'),
            content_disposition=dict(type='str'),
            cache_control=dict(type='str'),
            content_md5=dict(type='str'),
        )

        mutually_exclusive = [('src', 'dest')]

        self.blob_client = None
        self.blob_details = None
        self.storage_account_name = None
        self.blob = None
        self.blob_obj = None
        self.container = None
        self.container_obj = None
        self.dest = None
        self.force = None
        self.resource_group = None
        self.src = None
        self.state = None
        self.tags = None
        self.public_access = None
        self.results = dict(
            changed=False,
            actions=[],
            container=dict(),
            blob=dict()
        )

        super(AzureRMStorageBlob, self).__init__(derived_arg_spec=self.module_arg_spec,
                                                 supports_check_mode=True,
                                                 mutually_exclusive=mutually_exclusive,
                                                 supports_tags=True)

    def exec_module(self, **kwargs):

        for key in self.module_arg_spec.keys() + ['tags']:
            setattr(self, key, kwargs[key])

        self.results['check_mode'] = self.check_mode

        if not NAME_PATTERN.match(self.container):
            self.fail("Parameter error: container_name must consist of lowercase letters, "
                      "numbers and hyphens. It must begin with a letter or number. It may "
                      "not contain two consecutive hyphens.")

        # add file path validation

        self.blob_client = self.get_blob_client(self.resource_group, self.storage_account_name)
        self.container_obj = self.get_container()

        if self.blob is not None:
            self.blob_obj = self.get_blob()

        if self.state == 'present':
            if not self.container_obj:
                # create the container
                self.create_container()
            elif self.container_obj and not self.blob:
                # update container attributes
                update_tags, self.container_obj['tags'] = self.update_tags(self.container_obj.get('tags'))
                if update_tags:
                    self.update_container_tags(self.container_obj['tags'])

            if self.blob:
                # create, update or download blob
                if self.src and self.src_is_valid():
                    if self.blob_obj and not self.force:
                        self.log("Cannot upload to {0}. Blob with that name already exists. "
                            "Use the force option".format(self.blob))
                    else:
                        self.upload_blob()
                elif self.dest and self.dest_is_valid():
                    self.download_blob()

                update_tags, self.blob_obj['tags'] = self.update_tags(self.blob_obj.get('tags'))
                if update_tags:
                    self.update_blob_tags(self.blob_obj['tags'])

                if self.blob_content_settings_differ():
                    self.update_blob_content_settings()

        elif self.state == 'absent':
            if self.container_obj and not self.blob:
                # Delete container
                if self.container_has_blobs():
                    if self.force:
                        self.delete_container()
                    else:
                        self.log("Cannot delete container {0}. It contains blobs. Use the force option.".format(
                            self.container))
                else:
                    self.delete_container()
            elif self.container_obj and self.blob_obj:
                # Delete blob
                self.delete_blob()

        return self.results

    def get_container(self):
        result  = dict()
        container = None
        if self.container:
            try:
                container = self.blob_client.get_container_properties(self.container)
            except AzureMissingResourceHttpError:
                pass
        if container:
            result = dict(
                name=container.name,
                tags=container.metadata,
                last_mdoified=container.properties.last_modified.strftime('%d-%b-%Y %H:%M:%S %z'),
            )
        return result

    def get_blob(self):
        result = dict()
        blob = None
        if self.blob:
            try:
                blob = self.blob_client.get_blob_properties(self.container, self.blob)
            except AzureMissingResourceHttpError:
                pass
        if blob:
            result = dict(
                name=blob.name,
                tags=blob.metadata,
                last_modified=blob.properties.last_modified.strftime('%d-%b-%Y %H:%M:%S %z'),
                type=blob.properties.blob_type,
                content_length=blob.properties.content_length,
                content_settings=dict(
                    content_type=blob.properties.content_settings.content_type,
                    content_encoding=blob.properties.content_settings.content_encoding,
                    content_language=blob.properties.content_settings.content_language,
                    content_disposition=blob.properties.content_settings.content_disposition,
                    cache_control=blob.properties.content_settings.cache_control,
                    content_md5 =blob.properties.content_settings.content_md5
                )
            )
        return result

    def create_container(self):
        self.log('Create container %s' % self.container)

        tags = None
        if not self.blob and  self.tags:
            # when a blob is present, then tags are assigned at the blob level
            tags = self.tags

        if not self.check_mode:
            try:
                self.blob_client.create_container(self.container, metadata=tags, public_access=self.public_access)
            except AzureHttpError as exc:
                self.fail("Error creating container {0} - {1}".format(self.container, str(exc)))
        self.container_obj = self.get_container()
        self.results['changed'] = True
        self.results['actions'].append('created container {0}'.format(self.container))
        self.results['container'] = self.container_obj

    def upload_blob(self):
        content_settings = None
        if self.content_type or self.content_encoding or self.content_language or self.content_disposition or \
                self.cache_control or self.content_md5:
            content_settings = ContentSettings(
                content_type=self.content_type,
                content_encoding=self.content_encoding,
                content_language=self.content_language,
                content_disposition=self.content_disposition,
                cache_control=self.cache_control,
                content_md5=self.content_md5
            )
        if not self.check_mode:
            try:
                self.blob_client.create_blob_from_path(self.container, self.blob, self.src,
                                                       metadata=self.tags, content_settings=content_settings)
            except AzureHttpError as exc:
                self.fail("Error creating blob {0} - {1}".format(self.blob, str(exc)))

        self.blob_obj = self.get_blob()
        self.results['changed'] = True
        self.results['actions'].append('created blob {0} from {1}'.format(self.blob, self.src))
        self.results['container'] = self.container_obj
        self.results['blob'] = self.blob_obj

    def download_blob(self):
        if not self.check_mode:
            try:
                self.blob_client.get_blob_to_path(self.container, self.blob, self.dest)
            except Exception as exc:
                self.fail("Failed to download blob {0}:{1} to {2} - {3}".format(self.container,
                                                                                self.blob,
                                                                                self.dest,
                                                                                exc))
        self.results['changed'] = True
        self.results['actions'].append('downloaded blob {0}:{1} to {2}'.format(self.container,
                                                                               self.blob,
                                                                               self.dest))

        self.results['container'] = self.container_obj
        self.results['blob'] = self.blob_obj

    def src_is_valid(self):
        if not os.path.isfile(self.src):
            self.fail("The source path must be a file.")
        try:
            fp = open(self.src, 'r')
            fp.close()
        except IOError:
            self.fail("Failed to access {0}. Make sure the file exists and that you have "
                      "read access.".format(self.src))
        return True

    def dest_is_valid(self):
        if not self.check_mode:
            self.dest = os.path.expanduser(self.dest)
            self.dest = os.path.expandvars(self.dest)
            if not os.path.basename(self.dest):
                # dest is a directory
                if os.path.isdir(self.dest):
                    self.log("Path is dir. Appending blob name.")
                    self.dest += self.blob
                else:
                    try:
                        self.log('Attempting to makedirs {0}'.format(self.dest))
                        os.makddirs(self.dest)
                    except IOError as exc:
                        self.fail("Failed to create directory {0} - {1}".format(self.dest, str(exc)))
                    self.dest += self.blob
            else:
                # does path exist without basename
                file_name = os.path.basename(self.dest)
                path = self.dest.replace(file_name, '')
                self.log('Checking path {0}'.format(path))
                if not os.path.isdir(path):
                    try:
                        self.log('Attempting to makedirs {0}'.format(path))
                        os.makedirs(path)
                    except IOError as exc:
                        self.fail("Failed to create directory {0} - {1}".format(path, str(exc)))
            self.log('Checking final path {0}'.format(self.dest))
            if os.path.isfile(self.dest) and not self.force:
                # dest already exists and we're not forcing
                self.log("Dest {0} already exists. Cannot download. Use the force option.".format(self.dest))
                return False
        return True

    def delete_container(self):
        if not self.check_mode:
            try:
                self.blob_client.delete_container(self.container)
            except AzureHttpError as exc:
                self.fail("Error deleting container {0} - {1}".format(self.container, str(exc)))

        self.results['changed'] = True
        self.results['actions'].append('deleted container {0}'.format(self.container))

    def container_has_blobs(self):
        try:
            list_generator = self.blob_client.list_blobs(self.container)
        except AzureHttpError as exc:
            self.fail("Error list blobs in {0} - {1}".format(self.container, str(exc)))
        if len(list_generator.items) > 0:
            return True
        return False

    def delete_blob(self):
        if not self.check_mode:
            try:
                self.blob_client.delete_blob(self.container, self.blob)
            except AzureHttpError as exc:
                self.fail("Error deleting blob {0}:{1} - {2}".format(self.container, self.blob, str(exc)))

        self.results['changed'] = True
        self.results['actions'].append('deleted blob {0}:{1}'.format(self.container, self.blob))
        self.results['container'] = self.container_obj

    def update_container_tags(self, tags):
        if not self.check_mode:
            try:
                self.blob_client.set_container_metadata(self.container, metadata=tags)
            except AzureHttpError as exc:
                self.fail("Error updating container tags {0} - {1}".format(self.container, str(exc)))
        self.container_obj = self.get_container()
        self.results['changed'] = True
        self.results['actions'].append("updated container {0} tags.".format(self.container))
        self.results['container'] = self.container_obj

    def update_blob_tags(self, tags):
        if not self.check_mode:
            try:
                self.blob_client.set_blob_metadata(self.container, self.blob, metadata=tags)
            except AzureHttpError as exc:
                self.fail("Update blob tags {0}:{1} - {2}".format(self.container, self.blob, str(exc)))
        self.blob_obj = self.get_blob()
        self.results['changed'] = True
        self.results['actions'].append("updated blob {0}:{1} tags.".format(self.container, self.blob))
        self.results['container'] = self.container_obj
        self.results['blob'] = self.blob_obj

    def blob_content_settings_differ(self):
        if self.content_type or self.content_encoding or self.content_language or self.content_disposition or \
                self.cache_control or self.content_md5:
            settings = dict(
                content_type=self.content_type,
                content_encoding=self.content_encoding,
                content_language=self.content_language,
                content_disposition=self.content_disposition,
                cache_control=self.cache_control,
                content_md5=self.content_md5
            )
            if self.blob_obj['content_settings'] != settings:
                return True

        return False

    def update_blob_content_settings(self):
        content_settings = ContentSettings(
            content_type=self.content_type,
            content_encoding=self.content_encoding,
            content_language=self.content_language,
            content_disposition=self.content_disposition,
            cache_control=self.cache_control,
            content_md5=self.content_md5
        )
        if not self.check_mode:
            try:
                self.blob_client.set_blob_properties(self.container, self.blob, content_settings=content_settings)
            except AzureHttpError as exc:
                self.fail("Update blob content settings {0}:{1} - {2}".format(self.container, self.blob, str(exc)))

        self.blob_obj = self.get_blob()
        self.results['changed'] = True
        self.results['actions'].append("updated blob {0}:{1} content settings.".format(self.container, self.blob))
        self.results['container'] = self.container_obj
        self.results['blob'] = self.blob_obj


def main():
    AzureRMStorageBlob()

if __name__ == '__main__':
    main()