const std = @import("std");
const r4os = @import("r4os");
pub fn r4_app_main(app: *r4os.App) i32 {
    const sys=app.system();
    if(std.mem.eql(u8,app.args(),"child")) {sys.println("STUDIO_CHILD_OUTPUT");return 7;}
    if(std.mem.eql(u8,app.args(),"sleep")) {while(!sys.programShouldClose())sys.sleepTicks(2);sys.println("STUDIO_CHILD_CLOSED");return 0;}
    if(std.mem.eql(u8,app.args(),"busy")) {while(true)sys.sleepTicks(2);}
    const resources=r4os.Resources{.sys=sys};
    if(!resources.available()){sys.println("STUDIO_HANDLES_UNAVAILABLE");return 31;}
    var path:[256:0]u8=.{0} ** 256;
    if(sys.programModulePath(path[0..])<=0)return 32;
    var process=switch(resources.spawnWithConsoleHost(.{.ptr=&path,.len=@intCast(std.mem.sliceTo(&path,0).len)},"child",.console,.terminal_mode)) {.process=>|p|p,.failure=>|v|{sys.printI32(v);return 33;}};
    sys.write("STUDIO_GENERATION=");sys.printU64(process.generation);sys.println("");
    var stale=process;stale.generation+%=1;
    if(stale.kill()==0)return 34;
    const ready=process.waitReady(r4os.time_contract.timeoutFinite(.{.nanoseconds=5_000_000_000}));
    const completion=switch(ready){.ready=>|c|c,else=>return 35};
    if(completion.exit_code!=7)return 36;
    var output:[2048]u8=undefined;
    const count=switch(process.completionRead(0,&output)){.bytes=>|n|n,else=>return 37};
    sys.write(output[0..count]);
    switch(process.reap()){.exited=>|c|{if(c!=7)return 38;},else=>return 39}
    if(process.valid())return 40;
    process=switch(resources.spawnWithConsoleHost(.{.ptr=&path,.len=@intCast(std.mem.sliceTo(&path,0).len)},"sleep",.console,.terminal_mode)){.process=>|p|p,else=>return 41};
    sys.sleepTicks(10);
    if(process.requestClose()!=0)return 42;
    switch(process.wait(r4os.time_contract.timeoutFinite(.{.nanoseconds=5_000_000_000}))){.exited=>|v|{if(v!=0)return 43;},else=>return 44}
    process=switch(resources.spawnWithConsoleHost(.{.ptr=&path,.len=@intCast(std.mem.sliceTo(&path,0).len)},"busy",.console,.terminal_mode)){.process=>|p|p,else=>return 45};
    switch(process.waitReady(r4os.time_contract.timeoutFinite(.{.nanoseconds=25_000_000}))){.timed_out=>{},else=>return 46}
    if(process.kill()!=0)return 47;
    switch(process.wait(r4os.time_contract.timeoutFinite(.{.nanoseconds=5_000_000_000}))){.exited=>{},else=>return 48}
    sys.println("STUDIO_PROBE_OK handles=1 stale_rejected=1 close=1 timeout=1 kill=1 completion=1");
    return 0;
}
