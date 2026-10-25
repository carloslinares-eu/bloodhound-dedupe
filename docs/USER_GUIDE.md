# Bloodhound user guide

Bloodhound gathers one copy of every distinct file from a set of folders into a
single destination folder. It's meant for consolidating overlapping backups,
photo libraries, phone dumps and the like.

Your source folders are only ever **read**. Bloodhound writes only inside the
destination folder.

## The window

![The Bloodhound window](images/screenshot.png)

### Source folders

The folders to scan.

- **Add folders…** opens a folder picker. Select several folders at once with
  **Ctrl-click** (one by one) or **Shift-click** (a range), then confirm. To add
  folders from different places, click **Add folders…** again; folders already
  in the list are ignored.
  - On Windows this is the normal Windows folder dialog.
  - On macOS and Linux it is Bloodhound's own dialog: double-click a folder to
    open it, **Up** goes to the parent folder, and you can type a path in the box
    at the top. **Add selected** with nothing selected adds the folder you are in.
- **Remove selected** (or the **Delete** key) removes the highlighted folders.
  **Ctrl+A** in the list selects them all.
- **Clear** empties the list.

The **order matters**: when identical files exist in several folders, the one in
the folder nearest the top of the list is kept. Within a folder, files are read
alphabetically, and a folder's own files before its subfolders.

### Destination folder

Where the unique files are copied. It can be empty or already contain files from
an earlier run (see [Stopping and resuming](#stopping-and-resuming)).

Rules:

- The destination can't be one of the source folders or a folder that contains
  a source folder. Bloodhound refuses to start and explains why.
- The destination *may* be inside a source folder. It is then skipped while
  scanning, so earlier results are never treated as new input.

Inside the destination every source folder gets a subfolder named after it, with
its original structure underneath:

```text
<destination>\
├── Photos\2024\IMG_0001.jpg      ← D:\Photos\2024\IMG_0001.jpg
├── Photos (2)\IMG_0001.jpg       ← E:\Backup\Photos\IMG_0001.jpg (a different picture)
└── Drive F\notes.txt             ← F:\notes.txt (a whole drive was added)
```

Source folders with the same name are numbered (`Photos`, `Photos (2)`, …) so
their files can never overwrite each other.

### Worker threads

How many files are read, hashed and copied at the same time. The default is the
number of processor cores, up to 8.

| Storage | Suggested setting |
|---------|-------------------|
| SSD / NVMe | the default, or higher |
| Network share / NAS | 8–16 |
| Spinning hard drive (HDD) | 1–2: several simultaneous reads make the disk seek back and forth and slow everything down |
| Mixed | set it for the slowest drive involved |

### Progress

While a job runs the progress box shows:

- **Step N of 4** and its name (see [What happens during a job](#what-happens-during-a-job)).
- How many files of the step are done, and a file currently being worked on.
- **The progress bar**, with the amount of data processed and the total in
  KB/MB/GB, the percentage, and the current speed (e.g. `1.25 GB of 4.80 GB (26.0%) · 85.4 MB/s`).
  During step 1 the total isn't known yet, so the bar slides back and forth and
  shows how much data has been found so far.
- **Elapsed**: time since you pressed Start, for the whole job.
- **Remaining in this step**: the estimated time left for the current step, based
  on the speed over the last few seconds. It reads *estimating…* until there is
  enough data to estimate from.

Sizes use binary units, like Windows Explorer: 1 KB = 1024 bytes, 1 MB = 1024 KB, and so on.

## What happens during a job

1. **Scanning folders.** Every source folder is walked and each file's size
   recorded. Shortcuts to other folders (symbolic links and junctions) are not
   followed, to avoid scanning anything twice or looping forever.
2. **Comparing files.** A file whose size no other file shares can't have a
   duplicate, so it is not read at all in this step. Files that share a size are
   read in full and fingerprinted with SHA-256; identical fingerprints mean
   identical contents. Empty files all count as duplicates of each other, so one
   is kept.
3. **Copying unique files.** One copy of each unique file is copied, with its
   modification time and attributes. Each copy is written to a temporary
   `*.bloodhound-partial` file that replaces the final name only once it is
   complete.
4. **Verifying copies.** Each copy is read back and its SHA-256 compared with
   the source. A copy that doesn't match is copied again and checked once more.

At the end a summary shows how many files were scanned, how many were unique,
how many duplicates were skipped, what was copied and verified, and how long it took.

## Stopping and resuming

Click **Stop** at any time. Files that are mid-copy are abandoned and their
temporary files deleted; copies that were already finished stay in the destination.
Stopping takes at most a moment.

To **resume**, press **Start** again with the same source folders and destination.
Files already in the destination with the right size are not copied again.
Bloodhound reads their source to know what they should contain, and step 4 checks
them like any other copy, so a damaged copy from an interrupted run is still
caught and fixed.

Closing the window while a job runs asks for confirmation, stops the job, then quits.

## Problems with individual files

A file or folder that can't be read (no permission, removed while scanning, a
broken disk sector…) doesn't stop the job. It is skipped and listed when the job
ends; answer **Yes** to see the list, which can be copied to the clipboard.

## Troubleshooting

**"No module named tkinter" or "No module named _tkinter"** (Linux)
: Install Tkinter for your Python, e.g. `sudo apt install python3-tk`.

**It's slow on an external hard drive**
: Set **Worker threads** to 1 or 2.

**The remaining time jumps around**
: It covers only the current step and follows the speed of the last few seconds.
  Big files mixed with many small ones make the speed change, and the estimate with it.

**A copy keeps failing verification**
: The source file may be changing while it is copied (a file in use by another
  program), or the destination disk may be failing. The file is listed in the
  problems list at the end.

**I see `*.bloodhound-partial` files in the destination**
: They are left only if Bloodhound itself was killed mid-copy (for example from
  Task Manager or a power cut). They are safe to delete.
