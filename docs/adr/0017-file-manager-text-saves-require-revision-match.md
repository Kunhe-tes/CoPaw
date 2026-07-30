# File-manager text saves require a revision match

The Chat File Manager rejects a save when the editable text file has changed since the editor loaded it, retaining the user's unsaved draft rather than silently overwriting the newer file. This chooses explicit conflict resolution over last-writer-wins behavior because Agent activity and another browser view can modify the same tenant-scoped workspace file concurrently.
