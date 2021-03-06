import json
import os
import shutil
import subprocess
from types import SimpleNamespace

from bootstrap_modal_forms.generic import BSModalFormView
from dateutil.parser import parse
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http import FileResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.text import slugify
from django.views.generic import ListView, DetailView, UpdateView, CreateView
from django.utils.translation import gettext_lazy as _

from repository.callstack import push, delete_to, clear, peek
from repository.forms import RestoreForm, RepositoryForm, NewBackupForm
from repository.models import Repository, CallStack, Journal


def restic_command(repo, command):
    my_env = os.environ.copy()
    my_env["RESTIC_PASSWORD"] = repo.password

    if repo.sudo:
        command.insert(0, "sudo")

    return subprocess.run(command, stdout=subprocess.PIPE, env=my_env)


class RepositoryList(LoginRequiredMixin, ListView):
    model = Repository

    def get(self, request, *args, **kwargs):
        clear()
        return super(RepositoryList, self).get(request, *args, **kwargs)


class RepositoryUpdate(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Repository
    form_class = RepositoryForm
    success_message = _("Repository changed.")

    def get_success_url(self):
        return reverse("repository:list")


class RepositoryCreate(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Repository
    form_class = RepositoryForm
    success_message = _("Repository created")

    def get_success_url(self):
        return reverse("repository:list")

    def form_valid(self, form):
        path = os.path.join(
            settings.LOCAL_BACKUP_PATH, slugify(form.cleaned_data["name"])
        )

        my_env = os.environ.copy()
        my_env["RESTIC_PASSWORD"] = form.cleaned_data["password"]
        sudo = "sudo" in form.cleaned_data

        command = ["restic", "init", "-r", path]
        if sudo:
            command.insert(0, "sudo")

        result = subprocess.run(command, stdout=subprocess.PIPE, env=my_env)

        form.instance.path = path
        return super(RepositoryCreate, self).form_valid(form)


class RepositorySnapshots(LoginRequiredMixin, DetailView):
    model = Repository
    template_name = "repository/repository_snapshots.html"

    def get_context_data(self, **kwargs):
        clear()
        ctx = super(RepositorySnapshots, self).get_context_data(**kwargs)
        repo = self.get_object()

        command = ["restic", "-r", repo.path, "snapshots", "--json"]
        result = restic_command(repo, command)
        snapshots = json.loads(
            result.stdout, object_hook=lambda d: SimpleNamespace(**d)
        )
        if snapshots is not None:
            for snap in snapshots:
                snap.timestamp = parse(snap.time)
            ctx["snapshots"] = reversed(snapshots)
        else:
            ctx["snapshots"] = None
        return ctx


class FileBrowse(LoginRequiredMixin, DetailView):
    model = Repository

    def get(self, request, *args, **kwargs):
        request.session["view"] = kwargs.get("view", "icon")
        return super(FileBrowse, self).get(request, *args, **kwargs)

    def get_template_names(self):
        return ["repository/file_browse_{}.html".format(self.request.session["view"])]

    def get_context_data(self, **kwargs):
        short_id = self.request.GET.get("id", None)
        path = self.request.GET.get("path", None)

        ctx = super(FileBrowse, self).get_context_data(**kwargs)
        repo = self.get_object()

        command = ["restic", "-r", repo.path, "ls", short_id, path, "--json"]
        result = restic_command(repo, command)

        results = result.stdout.decode(encoding="UTF-8").split("\n")
        pathlist = []
        for item in results:
            try:
                if item != "":
                    json_item = json.loads(
                        item, object_hook=lambda d: SimpleNamespace(**d)
                    )
                    if json_item.struct_type == "snapshot":
                        snapshot = json_item
                    elif json_item.struct_type == "node":
                        if path == json_item.path:
                            delete_to(json_item.name)
                            push(json_item.name, json_item.path)
                        else:
                            pathlist.append(json_item)
                    else:
                        pass
            except:
                # import traceback
                # traceback.print_exc()
                pass

        ctx["snapshot"] = snapshot
        ctx["path_list"] = pathlist
        ctx["current"] = peek()
        ctx["stack"] = CallStack.objects.all()
        return ctx


class RestoreView(LoginRequiredMixin, BSModalFormView):
    form_class = RestoreForm
    template_name = "repository/restore_modal.html"
    success_url = "/"

    def get(self, request, *args, **kwargs):
        request.session["view"] = kwargs.get("view", "icon")
        request.session["repo_id"] = kwargs.get("pk", None)
        request.session["snapshot_id"] = request.GET.get("id", None)
        request.session["source_path"] = request.GET.get("path", None)
        request.session["return"] = request.GET.get("return", None)
        return super(RestoreView, self).get(request, *args, **kwargs)

    def get_success_url(self):
        if self.request.session["return"]:
            return reverse(
                "repository:snapshots", kwargs={"pk": self.request.session["repo_id"]}
            )
        else:
            rev_url = reverse(
                "repository:browse",
                kwargs={
                    "pk": self.request.session["repo_id"],
                    "view": self.request.session["view"],
                },
            )
            source_path = self.request.session["source_path"]
            parts = source_path.split("/")
            url = "{url}?id={id}&path={path}".format(
                url=rev_url,
                id=self.request.session["snapshot_id"],
                path="/".join(parts[:-1]),
            )
            return url

    def form_valid(self, form):
        if not self.request.is_ajax():
            snapshot_id = self.request.session["snapshot_id"]
            source_path = self.request.session["source_path"]
            dest_path = form.cleaned_data["path"]

            # restore to path
            repo = Repository.objects.get(pk=self.request.session["repo_id"])

            if dest_path == "":
                command = [
                    "restic",
                    "-r",
                    repo.path,
                    "restore",
                    snapshot_id,
                    "--include",
                    source_path,
                    "--target",
                    "/",
                ]
                msg = _("{src} successfully restored").format(
                    src=source_path, dest=dest_path
                )
                Journal.objects.create(
                    user=self.request.user, repo=repo, action="3", data=source_path
                )
            else:
                command = [
                    "restic",
                    "-r",
                    repo.path,
                    "restore",
                    snapshot_id,
                    "--include",
                    source_path,
                    "--target",
                    dest_path,
                ]
                msg = _("{src} successfully restored to {dest}").format(
                    src=source_path, dest=dest_path
                )
                Journal.objects.create(
                    user=self.request.user,
                    repo=repo,
                    action="3",
                    data="{} --> {}".format(source_path, dest_path),
                )
            result = restic_command(repo, command)
            messages.success(self.request, msg)
        return redirect(self.get_success_url())


class BackupView(LoginRequiredMixin, DetailView):
    model = Repository

    def get_success_url(self):
        return reverse(
            "repository:snapshots",
            kwargs={
                "pk": self.get_object().id,
            },
        )

    def get(self, request, *args, **kwargs):
        short_id = self.request.GET.get("id", None)
        path = self.request.GET.get("path", None)
        self.request.session["path"] = path
        self.request.session["short_id"] = short_id

        # backup path
        repo = self.get_object()
        command = ["restic", "-r", repo.path, "backup", path]
        result = restic_command(repo, command)
        Journal.objects.create(user=self.request.user, repo=repo, action="1", data=path)
        messages.success(
            self.request,
            _(
                "Backup of {path} successfully completed".format(
                    path=path,
                )
            ),
        )
        return redirect(self.get_success_url())


class NewBackupView(LoginRequiredMixin, BSModalFormView):
    form_class = NewBackupForm
    template_name = "repository/new_backup_modal.html"
    success_url = "/"

    def get(self, request, *args, **kwargs):
        request.session["repo_id"] = kwargs.get("pk", None)
        return super(NewBackupView, self).get(request, *args, **kwargs)

    def form_valid(self, form):
        if not self.request.is_ajax():
            path = form.cleaned_data["path"]

            # backup path
            repo = Repository.objects.get(pk=self.request.session["repo_id"])
            command = ["restic", "-r", repo.path, "backup", path]
            result = restic_command(repo, command)
            Journal.objects.create(
                user=self.request.user,
                repo=repo,
                action="1",
                data="{} --> {}".format(path),
            )
            messages.success(
                self.request,
                _(
                    "Backup of {path} successfully completed".format(
                        path=path,
                    )
                ),
            )
        return redirect(self.get_success_url())


class JournalView(LoginRequiredMixin, ListView):
    model = Journal


class Download(DetailView):
    model = Repository

    def get_success_url(self):
        if self.request.session["return"]:
            return reverse(
                "repository:snapshots", kwargs={"pk": self.request.session["repo_id"]}
            )
        else:
            rev_url = reverse(
                "repository:browse",
                kwargs={
                    "pk": self.request.session["repo_id"],
                    "view": self.request.session["view"],
                },
            )
            source_path = self.request.session["source_path"]
            parts = source_path.split("/")
            url = "{url}?id={id}&path={path}".format(
                url=rev_url,
                id=self.request.session["snapshot_id"],
                path="/".join(parts[:-1]),
            )
            return url

    def get(self, request, *args, **kwargs):
        request.session["view"] = kwargs.get("view", "icon")
        repo_id = kwargs.get("pk", None)
        snapshot_id = request.GET.get("id", None)
        path = request.GET.get("path", None)
        repo = Repository.objects.get(pk=repo_id)

        temp_path = getattr(settings, "TEMP_PATH", None)
        if temp_path is None:
            messages.error(
                self.request,
                _(
                    "You need to set the download path in localsetting.py to enable downloads"
                ),
            )
            return redirect(self.get_success_url())
        download_path = os.path.join(temp_path, slugify(repo.name))

        # restore to temp path
        command = [
            "restic",
            "-r",
            repo.path,
            "restore",
            snapshot_id,
            "--include",
            path,
            "--target",
            download_path,
        ]
        result = restic_command(repo, command)
        Journal.objects.create(
            user=self.request.user, repo=repo, action="2", data="{}".format(path)
        )

        zip_filename = "{}_{}".format(
            slugify(repo.name), os.path.basename(os.path.normpath(path))
        )
        zip_fullpath = os.path.join(temp_path, zip_filename)
        zip_dir = os.path.dirname((os.path.join(download_path, path[1:])))
        shutil.make_archive(zip_fullpath, "zip", zip_dir)

        zip_name = zip_filename + ".zip"
        zip_fullpath = os.path.join(temp_path, zip_name)

        zip_file = open(zip_fullpath, "rb")
        resp = FileResponse(zip_file, content_type="application/force-download")
        resp["Content-Disposition"] = "attachment; filename=%s" % zip_name

        os.remove(zip_fullpath)
        shutil.rmtree(download_path)
        return resp
