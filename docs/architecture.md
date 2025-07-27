# New architecture idea

* BitTTY becomes the main terminal class
* you can add stuff to it with .add(), which registers a device
* devices register to receive signals, which are blocks of data wrapped in a
  message

So, for a UNIX terminal:

    tty = BiTTY()
    tty.add(UNIXPty("some program"))
    tty.add(TerminalInput())
    tty.add(TerminalDisplay())

Or maybe you want a printer?

    tty.add(Printer())



