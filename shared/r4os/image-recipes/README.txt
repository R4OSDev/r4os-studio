Studio project image consumers

These companion source files are for the selected app, not replacements for SDK
or Contract files. Copy only the selected language helper into project sources.
Use the project's existing SDK/Contract/compiler pins and read their bindings.
Qualification: SDK0.64.92/51ed03d8, Contract0.64.45/db155842, Zig0.16.0,
Rust1.99.0. Earlier/later projects must verify their actual method/ABI contracts;
Studio does not switch their pins or keep a revision allowlist.

1. Import a confirmed Studio image. Use the returned actual path, dimensions,
   format, stride, alpha treatment and hash. Keep the private original.
2. For a desktop icon use ICON=<actual path>. The bitmap ICO includes a32x32
   entry. For an image the app reads by name use RESOURCE=SCENE:<actual path>.
   Each named resource is unique. The Assets directory alone embeds nothing.
3. Read the current app's own module path, then moduleResourceRead with type3,
   index0 and the exact resource name. Type1/index0 reads the first ICON entry.
   A known path to a different module is not a replacement for the own-module
   path. Check both returned status and exact expected resource size.
4. ICO: use the SDK decoder in Zig; the C/Rust helper accepts Studio32-bit
   uncompressed bitmap entries. PNG bytes or PNG-compressed ICOs do not meet
   this decoder contract. Choose the returned icon dimensions; check capacities.
5. Raw .rgba: project-specific headerless top-down RGBA32, straight alpha,
   stride=width*4. It is not an OS file format. Validate exact length and use
   the receipt's dimensions. Helpers composite alpha onto an explicit background
   and produce0x00RRGGBB for R4DRAW. They tile larger images to the pinned ABI's
   raster bounds, currently128x128. Provide caller-owned scratch outside a small
   stack and draw only during a valid current window paint.
6. Return a clear app error such as "Image resource missing, changed or unsupported"
   if path/read/length/decoder/draw checks fail. Do not draw uninitialized bytes.
7. Build with the normal Studio tool and check resourceInventory.stage=Embedded,
   artifact/source/manifest identity, payload names/indices/lengths/SHA-256.
   consumerVerified/guestVerified are separate. Report a guest visual check only
   after actually observing it with the existing authorized runner.

No helper calls a model, downloads a decoder, changes pins or authorizes a VM,
Remote Host, GitHub push, Goal change or Roadmap cleanup. Use fixed existing
image bytes for rebuilds. Failure, interruption or a lost reply never grants
permission to generate or import again automatically.

Small call patterns (use caller-owned, adequately sized buffers):

Zig, named toolbar ICO:
  const sys = app.system();
  const bytes = images.own(&sys,3,0,"TOOLBAR.ICO",&iconBytes) orelse return -20;
  const icon = images.icon(bytes,32,&pixels,background) orelse return -21;
  if(images.draw(paint.canvas,16,16,icon.width,icon.height,&pixels,&scratch)<0)
      return -22;

C, named toolbar ICO:
  int32_t count=studio_image_read(app,3,0,"TOOLBAR.ICO",icon_bytes,sizeof icon_bytes);
  if(count<=0 || !studio_icon(icon_bytes,(size_t)count,32,pixels,pixel_capacity,
                             background,&width,&height)) return -20;
  if(studio_image_draw(canvas,16,16,width,height,pixels,pixel_capacity,
                       scratch,scratch_capacity)<0) return -21;

Rust, named toolbar ICO:
  let count=images::read(app,3,0,c"TOOLBAR.ICO",icon_bytes).ok_or(-20)?;
  let (w,h)=images::icon(&icon_bytes[..count],32,pixels,background).ok_or(-21)?;
  if !images::draw(paint,16,16,w as u32,h as u32,pixels,scratch){return Err(-22);}

For the larger scene use RESOURCE=SCENE:<returned .rgba path>, read name SCENE,
require count == width*height*4 from the import receipt, and call rgba with that
exact stride before drawing. For a desktop application icon use ICON=<returned
.ico path>; it is the type1/index0 module resource, separately from a named
RESOURCE=TOOLBAR.ICO entry. Do not replace the app's window lifecycle or startup
contract to copy these small call patterns. If a resource is missing or rejected,
show the app error instead of painting a fake successful result.
