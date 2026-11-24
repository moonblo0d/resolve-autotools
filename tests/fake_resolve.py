"""In-memory stand-in for the DaVinci Resolve scripting API (only what resolve_autotools uses).

Method names and return types follow the official README (Resolve 20.1).
"""

from __future__ import annotations

import os

from resolve_autotools.media import AUDIO_EXT, IMAGE_EXT
from resolve_autotools.timecode import FrameRate, frames_to_tc

HOUR_24FPS = 86400  # 01:00:00:00 at 24 fps


class FakeMediaPoolItem:
    def __init__(self, name, path, clip_type="Video", frames=48):
        self.name, self.frames = name, frames
        self.props = {"Type": clip_type, "File Path": path, "Frames": str(frames)}

    def GetName(self):
        return self.name

    def GetClipProperty(self, key=None):
        return dict(self.props) if key is None else self.props.get(key, "")


class FakeFolder:
    def __init__(self, name):
        self.name, self.subfolders, self.clips = name, [], []

    def GetName(self):
        return self.name

    def GetSubFolderList(self):
        return list(self.subfolders)

    def GetClipList(self):
        return list(self.clips)


class FakeTimelineItem:
    def __init__(self, pool_item, start):
        self.pool_item, self.start = pool_item, start
        self.end = start + pool_item.frames

    def GetName(self):
        return self.pool_item.GetName()

    def GetStart(self, subframe_precision=False):
        return self.start

    def GetEnd(self, subframe_precision=False):
        return self.end

    def GetDuration(self, subframe_precision=False):
        return self.end - self.start

    def GetMediaPoolItem(self):
        return self.pool_item


class FakeTimeline:
    def __init__(self, name, clips=(), fps="24", start_frame=HOUR_24FPS):
        self.name, self.fps, self.start_frame = name, fps, start_frame
        self.tracks = {1: []}
        self.markers = {}
        position = start_frame
        for clip in clips:
            item = FakeTimelineItem(clip, position)
            self.tracks[1].append(item)
            position = item.end

    def GetName(self):
        return self.name

    def GetSetting(self, key=None):
        return {"timelineFrameRate": self.fps, "timelineDropFrameTimecode": "0"}.get(key, "")

    def GetStartFrame(self):
        return self.start_frame

    def GetEndFrame(self):
        items = [i for track in self.tracks.values() for i in track]
        return max((i.end for i in items), default=self.start_frame)

    def GetStartTimecode(self):
        return frames_to_tc(self.start_frame, FrameRate.parse(self.fps))

    def GetTrackCount(self, track_type):
        return len(self.tracks) if track_type == "video" else 0

    def GetItemListInTrack(self, track_type, index):
        return list(self.tracks.get(index, [])) if track_type == "video" else []

    def AddMarker(self, frame_id, color, name, note, duration, custom_data=""):
        if frame_id in self.markers:
            return False
        self.markers[frame_id] = {"color": color, "name": name, "note": note, "duration": duration}
        return True

    def GetMarkers(self):
        return dict(self.markers)


class FakeMediaPool:
    def __init__(self, project):
        self.project = project
        self.root = FakeFolder("Master")
        self.current = self.root
        self.import_calls = []

    def GetRootFolder(self):
        return self.root

    def AddSubFolder(self, folder, name):
        sub = FakeFolder(name)
        folder.subfolders.append(sub)
        return sub

    def SetCurrentFolder(self, folder):
        self.current = folder
        return True

    def ImportMedia(self, items):
        self.import_calls.append(list(items))
        created = []
        for item in items:
            if isinstance(item, dict):
                pattern = os.path.basename(item["FilePath"])
                frames = item["EndIndex"] - item["StartIndex"] + 1
                clip = FakeMediaPoolItem(pattern, item["FilePath"], "Video", frames)
            else:
                name = os.path.basename(item)
                ext = name.rsplit(".", 1)[-1].lower()
                clip_type = "Audio" if ext in AUDIO_EXT else "Still" if ext in IMAGE_EXT else "Video"
                clip = FakeMediaPoolItem(name, item, clip_type)
            self.current.clips.append(clip)
            created.append(clip)
        return created

    def CreateTimelineFromClips(self, name, clips):
        timeline = FakeTimeline(name, clips)
        self.project.timelines.append(timeline)
        self.project.current = timeline
        return timeline


class FakeProject:
    def __init__(self, name="Demo Project", timelines=(), presets=("YouTube - 1080p", "H.264 Master")):
        self.name = name
        self.media_pool = FakeMediaPool(self)
        self.timelines = list(timelines)
        self.current = self.timelines[0] if self.timelines else None
        self.presets = list(presets)
        self.loaded_preset = None
        self.settings_log = []
        self.jobs = {}
        self.polls_left = 0

    # timelines
    def GetName(self):
        return self.name

    def GetMediaPool(self):
        return self.media_pool

    def GetTimelineCount(self):
        return len(self.timelines)

    def GetTimelineByIndex(self, idx):
        return self.timelines[idx - 1]

    def GetCurrentTimeline(self):
        return self.current

    def SetCurrentTimeline(self, timeline):
        if timeline not in self.timelines:
            return False
        self.current = timeline
        return True

    # render
    def GetRenderPresetList(self):
        return list(self.presets)

    def LoadRenderPreset(self, name):
        if name not in self.presets:
            return False
        self.loaded_preset = name
        return True

    def SetRenderSettings(self, settings):
        self.settings_log.append({"timeline": self.current.GetName(), **settings})
        return True

    def AddRenderJob(self):
        job_id = f"job-{len(self.jobs) + 1}"
        self.jobs[job_id] = {"timeline": self.current.GetName(), "preset": self.loaded_preset,
                             **self.settings_log[-1], "JobStatus": "Ready", "CompletionPercentage": 0}
        return job_id

    def StartRendering(self, job_ids=None, isInteractiveMode=False):
        if any(j not in self.jobs for j in job_ids or []):
            return False
        self.polls_left = 2
        for job in self.jobs.values():
            job.update(JobStatus="Rendering", CompletionPercentage=50)
        return True

    def IsRenderingInProgress(self):
        if self.polls_left <= 0:
            for job in self.jobs.values():
                job.update(JobStatus="Complete", CompletionPercentage=100)
            return False
        self.polls_left -= 1
        return True

    def GetRenderJobStatus(self, job_id):
        job = self.jobs.get(job_id)
        return {"JobStatus": job["JobStatus"], "CompletionPercentage": job["CompletionPercentage"]} if job else {}


class FakeProjectManager:
    def __init__(self, project):
        self.project = project

    def GetCurrentProject(self):
        return self.project


class FakeResolve:
    def __init__(self, project=None):
        self.manager = FakeProjectManager(project)

    def GetProjectManager(self):
        return self.manager

    def GetProductName(self):
        return "DaVinci Resolve Studio"

    def GetVersionString(self):
        return "20.1.0.20"


def demo_resolve():
    """A project with one 2-clip timeline (01:00:00:00, 24 fps, 48 frames per clip)."""
    clips = [FakeMediaPoolItem("intro.mov", r"D:\media\intro.mov"),
             FakeMediaPoolItem("interview.mov", r"D:\media\interview.mov")]
    timeline = FakeTimeline("Edit v1", clips)
    return FakeResolve(FakeProject(timelines=[timeline, FakeTimeline("Shorts cut", clips[:1])]))
