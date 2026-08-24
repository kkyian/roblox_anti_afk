#import <ApplicationServices/ApplicationServices.h>
#import <Cocoa/Cocoa.h>
#import <QuartzCore/QuartzCore.h>
#import <unistd.h>

typedef NS_ENUM(NSInteger, AAFAction) {
    AAFActionSpace = 0,
    AAFActionClick = 1,
    AAFActionNudge = 2,
};

static NSString *AAFActionTitle(AAFAction action) {
    switch (action) {
        case AAFActionSpace:
            return @"Space key";
        case AAFActionClick:
            return @"Left click";
        case AAFActionNudge:
            return @"Mouse nudge";
    }
    return @"Unknown";
}

static NSString *AAFActionDetail(AAFAction action) {
    switch (action) {
        case AAFActionSpace:
            return @"Taps Space in the active Roblox window.";
        case AAFActionClick:
            return @"Clicks at the current mouse position.";
        case AAFActionNudge:
            return @"Moves the pointer 1 pixel and back.";
    }
    return @"Choose a supported action.";
}

static BOOL AAFSetError(NSError **error, NSString *message) {
    if (error != NULL) {
        *error = [NSError errorWithDomain:@"RobloxAntiAFK"
                                     code:1
                                 userInfo:@{NSLocalizedDescriptionKey: message}];
    }
    return NO;
}

static NSString *AAFSecondsLabel(NSInteger seconds) {
    if (seconds <= 0) {
        return @"now";
    }

    NSInteger minutes = seconds / 60;
    NSInteger remainder = seconds % 60;
    if (minutes == 0) {
        return [NSString stringWithFormat:@"%lds", (long)remainder];
    }
    return [NSString stringWithFormat:@"%ldm %02lds", (long)minutes, (long)remainder];
}

static NSTextField *AAFLabel(NSString *text, NSRect frame, CGFloat size, NSFontWeight weight, NSColor *color) {
    NSTextField *label = [NSTextField labelWithString:text];
    label.frame = frame;
    label.font = [NSFont systemFontOfSize:size weight:weight];
    label.textColor = color;
    label.lineBreakMode = NSLineBreakByWordWrapping;
    label.maximumNumberOfLines = 0;
    return label;
}

static NSView *AAFPanel(NSRect frame) {
    NSView *panel = [[NSView alloc] initWithFrame:frame];
    panel.wantsLayer = YES;
    panel.layer.cornerRadius = 8.0;
    panel.layer.borderWidth = 1.0;
    panel.layer.borderColor = [[NSColor colorWithCalibratedWhite:0.82 alpha:1.0] CGColor];
    panel.layer.backgroundColor = [[NSColor controlBackgroundColor] CGColor];
    return panel;
}

@interface AAFInputController : NSObject
- (BOOL)isAccessibilityTrusted;
- (BOOL)performAction:(AAFAction)action error:(NSError **)error;
- (NSNumber *)isRobloxActive;
- (void)openAccessibilitySettings;
@end

@implementation AAFInputController

- (BOOL)isAccessibilityTrusted {
    return AXIsProcessTrusted();
}

- (BOOL)performAction:(AAFAction)action error:(NSError **)error {
    if (![self isAccessibilityTrusted]) {
        return AAFSetError(error, @"Enable Accessibility access for Roblox Anti-AFK before starting.");
    }

    switch (action) {
        case AAFActionSpace:
            return [self pressSpaceWithError:error];
        case AAFActionClick:
            return [self leftClickWithError:error];
        case AAFActionNudge:
            return [self mouseNudgeWithError:error];
    }
}

- (NSNumber *)isRobloxActive {
    NSRunningApplication *app = [[NSWorkspace sharedWorkspace] frontmostApplication];
    if (app == nil) {
        return nil;
    }

    NSString *name = app.localizedName ?: @"";
    NSString *bundle = app.bundleIdentifier ?: @"";
    NSString *executable = app.executableURL.lastPathComponent ?: @"";
    NSString *text = [[NSString stringWithFormat:@"%@ %@ %@", name, bundle, executable] lowercaseString];
    return @([text containsString:@"roblox"]);
}

- (void)openAccessibilitySettings {
    NSURL *url = [NSURL URLWithString:@"x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"];
    if (url != nil) {
        [[NSWorkspace sharedWorkspace] openURL:url];
    }
}

- (BOOL)pressSpaceWithError:(NSError **)error {
    CGEventRef down = CGEventCreateKeyboardEvent(NULL, 49, true);
    CGEventRef up = CGEventCreateKeyboardEvent(NULL, 49, false);
    if (down == NULL || up == NULL) {
        if (down != NULL) {
            CFRelease(down);
        }
        if (up != NULL) {
            CFRelease(up);
        }
        return AAFSetError(error, @"Could not create a Space key event.");
    }

    CGEventPost(kCGHIDEventTap, down);
    usleep(50000);
    CGEventPost(kCGHIDEventTap, up);
    CFRelease(down);
    CFRelease(up);
    return YES;
}

- (BOOL)leftClickWithError:(NSError **)error {
    CGPoint point;
    if (![self currentMousePoint:&point error:error]) {
        return NO;
    }

    CGEventRef down = CGEventCreateMouseEvent(NULL, kCGEventLeftMouseDown, point, kCGMouseButtonLeft);
    CGEventRef up = CGEventCreateMouseEvent(NULL, kCGEventLeftMouseUp, point, kCGMouseButtonLeft);
    if (down == NULL || up == NULL) {
        if (down != NULL) {
            CFRelease(down);
        }
        if (up != NULL) {
            CFRelease(up);
        }
        return AAFSetError(error, @"Could not create a mouse click event.");
    }

    CGEventPost(kCGHIDEventTap, down);
    usleep(50000);
    CGEventPost(kCGHIDEventTap, up);
    CFRelease(down);
    CFRelease(up);
    return YES;
}

- (BOOL)mouseNudgeWithError:(NSError **)error {
    CGPoint point;
    if (![self currentMousePoint:&point error:error]) {
        return NO;
    }

    CGPoint nudged = CGPointMake(point.x + 1.0, point.y);
    CGEventRef moveOut = CGEventCreateMouseEvent(NULL, kCGEventMouseMoved, nudged, kCGMouseButtonLeft);
    CGEventRef moveBack = CGEventCreateMouseEvent(NULL, kCGEventMouseMoved, point, kCGMouseButtonLeft);
    if (moveOut == NULL || moveBack == NULL) {
        if (moveOut != NULL) {
            CFRelease(moveOut);
        }
        if (moveBack != NULL) {
            CFRelease(moveBack);
        }
        return AAFSetError(error, @"Could not create a mouse movement event.");
    }

    CGEventPost(kCGHIDEventTap, moveOut);
    usleep(50000);
    CGEventPost(kCGHIDEventTap, moveBack);
    CFRelease(moveOut);
    CFRelease(moveBack);
    return YES;
}

- (BOOL)currentMousePoint:(CGPoint *)point error:(NSError **)error {
    CGEventRef event = CGEventCreate(NULL);
    if (event == NULL) {
        return AAFSetError(error, @"Could not read the current mouse position.");
    }

    *point = CGEventGetLocation(event);
    CFRelease(event);
    return YES;
}

@end

@interface AAFEngine : NSObject
@property(nonatomic, copy) void (^onChange)(void);
@property(nonatomic, readonly) BOOL running;
@property(nonatomic, readonly) NSDate *nextActionDate;
@property(nonatomic, readonly) NSInteger actionCount;
@property(nonatomic, readonly) NSArray<NSDictionary<NSString *, NSString *> *> *events;
- (BOOL)isAccessibilityTrusted;
- (void)openAccessibilitySettings;
- (void)startWithInterval:(NSInteger)interval jitter:(NSInteger)jitter action:(AAFAction)action requireFocus:(BOOL)requireFocus;
- (void)stop;
@end

@interface AAFEngine ()
@property(nonatomic) BOOL running;
@property(nonatomic) NSInteger interval;
@property(nonatomic) NSInteger jitter;
@property(nonatomic) AAFAction action;
@property(nonatomic) BOOL requireFocus;
@property(nonatomic, strong) NSDate *nextActionDate;
@property(nonatomic, strong) NSDate *lastActionDate;
@property(nonatomic) NSInteger actionCount;
@property(nonatomic, copy) NSString *lastError;
@property(nonatomic, strong) NSMutableArray<NSDictionary<NSString *, NSString *> *> *mutableEvents;
@property(nonatomic, strong) NSTimer *timer;
@property(nonatomic, strong) NSDateFormatter *dateFormatter;
@property(nonatomic, strong) AAFInputController *input;
@end

@implementation AAFEngine

- (instancetype)init {
    self = [super init];
    if (self != nil) {
        _interval = 180;
        _jitter = 15;
        _action = AAFActionSpace;
        _requireFocus = YES;
        _mutableEvents = [NSMutableArray array];
        _input = [[AAFInputController alloc] init];
        _dateFormatter = [[NSDateFormatter alloc] init];
        _dateFormatter.dateFormat = @"HH:mm:ss";
    }
    return self;
}

- (NSArray<NSDictionary<NSString *, NSString *> *> *)events {
    return [self.mutableEvents copy];
}

- (BOOL)isAccessibilityTrusted {
    return [self.input isAccessibilityTrusted];
}

- (void)openAccessibilitySettings {
    [self.input openAccessibilitySettings];
}

- (void)startWithInterval:(NSInteger)interval jitter:(NSInteger)jitter action:(AAFAction)action requireFocus:(BOOL)requireFocus {
    self.interval = interval;
    self.jitter = jitter;
    self.action = action;
    self.requireFocus = requireFocus;
    self.lastError = nil;

    if (self.running) {
        [self log:@"Settings updated."];
        [self scheduleNextInitial:NO];
        return;
    }

    self.running = YES;
    self.actionCount = 0;
    self.lastActionDate = nil;
    [self log:@"Started. First action is armed."];
    [self scheduleNextInitial:YES];
}

- (void)stop {
    if (!self.running) {
        return;
    }

    [self.timer invalidate];
    self.timer = nil;
    self.running = NO;
    self.nextActionDate = nil;
    [self log:@"Stopped."];
    [self notify];
}

- (void)scheduleNextInitial:(BOOL)initial {
    [self.timer invalidate];

    NSInteger delay = 5;
    if (!initial) {
        NSInteger spread = self.jitter;
        NSInteger offset = 0;
        if (spread > 0) {
            uint32_t range = (uint32_t)((spread * 2) + 1);
            offset = (NSInteger)arc4random_uniform(range) - spread;
        }
        delay = MAX(5, self.interval + offset);
    }

    self.nextActionDate = [NSDate dateWithTimeIntervalSinceNow:(NSTimeInterval)delay];
    self.timer = [NSTimer scheduledTimerWithTimeInterval:(NSTimeInterval)delay
                                                  target:self
                                                selector:@selector(fireTimer:)
                                                userInfo:nil
                                                 repeats:NO];
    [self notify];
}

- (void)fireTimer:(NSTimer *)timer {
    if (!self.running) {
        return;
    }

    if (self.requireFocus) {
        NSNumber *robloxActive = [self.input isRobloxActive];
        if (robloxActive == nil) {
            [self log:@"Skipped because the active app could not be checked."];
            [self scheduleNextInitial:NO];
            return;
        }

        if (![robloxActive boolValue]) {
            [self log:@"Skipped because Roblox is not active."];
            [self scheduleNextInitial:NO];
            return;
        }
    }

    NSError *error = nil;
    if ([self.input performAction:self.action error:&error]) {
        self.actionCount += 1;
        self.lastActionDate = [NSDate date];
        self.lastError = nil;
        [self log:[NSString stringWithFormat:@"Sent action: %@.", AAFActionTitle(self.action)]];
    } else {
        self.lastError = error.localizedDescription ?: @"Input failed.";
        [self log:[NSString stringWithFormat:@"Error: %@", self.lastError]];
    }

    [self scheduleNextInitial:NO];
}

- (void)log:(NSString *)message {
    NSString *time = [self.dateFormatter stringFromDate:[NSDate date]];
    [self.mutableEvents insertObject:@{@"time": time, @"message": message} atIndex:0];
    if (self.mutableEvents.count > 80) {
        [self.mutableEvents removeObjectsInRange:NSMakeRange(80, self.mutableEvents.count - 80)];
    }
    [self notify];
}

- (void)notify {
    if (self.onChange != nil) {
        self.onChange();
    }
}

@end

@interface MainViewController : NSViewController
@end

@interface MainViewController ()
@property(nonatomic, strong) AAFEngine *engine;
@property(nonatomic, strong) NSTextField *statusPill;
@property(nonatomic, strong) NSTextField *intervalField;
@property(nonatomic, strong) NSTextField *jitterField;
@property(nonatomic, strong) NSPopUpButton *actionPopup;
@property(nonatomic, strong) NSTextField *actionDetailLabel;
@property(nonatomic, strong) NSButton *focusGuardButton;
@property(nonatomic, strong) NSButton *startButton;
@property(nonatomic, strong) NSButton *stopButton;
@property(nonatomic, strong) NSTextField *nextActionValue;
@property(nonatomic, strong) NSTextField *actionCountValue;
@property(nonatomic, strong) NSTextField *permissionValue;
@property(nonatomic, strong) NSTextField *permissionNotice;
@property(nonatomic, strong) NSTextView *logTextView;
@property(nonatomic, strong) NSTimer *refreshTimer;
@end

@implementation MainViewController

- (void)loadView {
    self.view = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 840, 640)];
    self.view.wantsLayer = YES;
    self.view.layer.backgroundColor = [[NSColor windowBackgroundColor] CGColor];
}

- (void)viewDidLoad {
    [super viewDidLoad];
    self.engine = [[AAFEngine alloc] init];
    [self buildInterface];

    __weak MainViewController *weakSelf = self;
    self.engine.onChange = ^{
        [weakSelf refreshStatus];
    };

    [self refreshStatus];
    self.refreshTimer = [NSTimer scheduledTimerWithTimeInterval:1.0
                                                         target:self
                                                       selector:@selector(refreshStatus)
                                                       userInfo:nil
                                                        repeats:YES];
}

- (void)dealloc {
    [self.refreshTimer invalidate];
    [self.engine stop];
}

- (void)buildInterface {
    [self.view addSubview:AAFLabel(@"Roblox Anti-AFK",
                                   NSMakeRect(24, 586, 360, 34),
                                   28,
                                   NSFontWeightBold,
                                   [NSColor labelColor])];

    self.statusPill = AAFLabel(@"Stopped",
                               NSMakeRect(696, 590, 120, 30),
                               13,
                               NSFontWeightSemibold,
                               [NSColor secondaryLabelColor]);
    self.statusPill.alignment = NSTextAlignmentCenter;
    self.statusPill.wantsLayer = YES;
    self.statusPill.layer.cornerRadius = 15.0;
    self.statusPill.layer.backgroundColor = [[NSColor controlBackgroundColor] CGColor];
    [self.view addSubview:self.statusPill];

    NSView *controls = AAFPanel(NSMakeRect(24, 330, 520, 230));
    NSView *status = AAFPanel(NSMakeRect(568, 330, 248, 230));
    NSView *activity = AAFPanel(NSMakeRect(24, 24, 792, 280));
    [self.view addSubview:controls];
    [self.view addSubview:status];
    [self.view addSubview:activity];

    [self buildControlsPanel:controls];
    [self buildStatusPanel:status];
    [self buildActivityPanel:activity];
}

- (void)buildControlsPanel:(NSView *)panel {
    [panel addSubview:AAFLabel(@"Controls", NSMakeRect(16, 194, 160, 22), 17, NSFontWeightSemibold, [NSColor labelColor])];
    [panel addSubview:AAFLabel(@"Interval seconds", NSMakeRect(16, 160, 150, 18), 12, NSFontWeightSemibold, [NSColor secondaryLabelColor])];
    [panel addSubview:AAFLabel(@"Jitter seconds", NSMakeRect(192, 160, 150, 18), 12, NSFontWeightSemibold, [NSColor secondaryLabelColor])];

    self.intervalField = [[NSTextField alloc] initWithFrame:NSMakeRect(16, 128, 150, 28)];
    self.intervalField.stringValue = @"180";
    self.intervalField.alignment = NSTextAlignmentRight;
    self.intervalField.font = [NSFont systemFontOfSize:14 weight:NSFontWeightSemibold];
    [panel addSubview:self.intervalField];

    self.jitterField = [[NSTextField alloc] initWithFrame:NSMakeRect(192, 128, 150, 28)];
    self.jitterField.stringValue = @"15";
    self.jitterField.alignment = NSTextAlignmentRight;
    self.jitterField.font = [NSFont systemFontOfSize:14 weight:NSFontWeightSemibold];
    [panel addSubview:self.jitterField];

    [panel addSubview:AAFLabel(@"Action", NSMakeRect(16, 92, 100, 18), 12, NSFontWeightSemibold, [NSColor secondaryLabelColor])];
    self.actionPopup = [[NSPopUpButton alloc] initWithFrame:NSMakeRect(16, 60, 210, 30) pullsDown:NO];
    [self.actionPopup addItemWithTitle:AAFActionTitle(AAFActionSpace)];
    [self.actionPopup addItemWithTitle:AAFActionTitle(AAFActionClick)];
    [self.actionPopup addItemWithTitle:AAFActionTitle(AAFActionNudge)];
    self.actionPopup.target = self;
    self.actionPopup.action = @selector(actionChanged:);
    [panel addSubview:self.actionPopup];

    self.actionDetailLabel = AAFLabel(AAFActionDetail(AAFActionSpace),
                                      NSMakeRect(244, 52, 246, 44),
                                      12,
                                      NSFontWeightRegular,
                                      [NSColor secondaryLabelColor]);
    [panel addSubview:self.actionDetailLabel];

    self.focusGuardButton = [NSButton checkboxWithTitle:@"Roblox focus guard" target:nil action:nil];
    self.focusGuardButton.frame = NSMakeRect(16, 20, 180, 24);
    self.focusGuardButton.state = NSControlStateValueOn;
    [panel addSubview:self.focusGuardButton];

    [panel addSubview:AAFLabel(@"Only sends input while Roblox is active.",
                               NSMakeRect(198, 17, 170, 34),
                               12,
                               NSFontWeightRegular,
                               [NSColor secondaryLabelColor])];

    self.startButton = [NSButton buttonWithTitle:@"Start" target:self action:@selector(startTapped:)];
    self.startButton.frame = NSMakeRect(386, 20, 54, 30);
    self.startButton.bezelStyle = NSBezelStyleRounded;
    self.startButton.keyEquivalent = @"\r";
    [panel addSubview:self.startButton];

    self.stopButton = [NSButton buttonWithTitle:@"Stop" target:self action:@selector(stopTapped:)];
    self.stopButton.frame = NSMakeRect(448, 20, 54, 30);
    self.stopButton.bezelStyle = NSBezelStyleRounded;
    self.stopButton.enabled = NO;
    [panel addSubview:self.stopButton];
}

- (void)buildStatusPanel:(NSView *)panel {
    [panel addSubview:AAFLabel(@"Status", NSMakeRect(16, 194, 160, 22), 17, NSFontWeightSemibold, [NSColor labelColor])];

    [panel addSubview:AAFLabel(@"Next action", NSMakeRect(16, 158, 110, 18), 12, NSFontWeightSemibold, [NSColor secondaryLabelColor])];
    self.nextActionValue = AAFLabel(@"-", NSMakeRect(130, 158, 88, 18), 13, NSFontWeightBold, [NSColor labelColor]);
    self.nextActionValue.alignment = NSTextAlignmentRight;
    [panel addSubview:self.nextActionValue];

    [panel addSubview:AAFLabel(@"Actions sent", NSMakeRect(16, 128, 110, 18), 12, NSFontWeightSemibold, [NSColor secondaryLabelColor])];
    self.actionCountValue = AAFLabel(@"0", NSMakeRect(130, 128, 88, 18), 13, NSFontWeightBold, [NSColor labelColor]);
    self.actionCountValue.alignment = NSTextAlignmentRight;
    [panel addSubview:self.actionCountValue];

    [panel addSubview:AAFLabel(@"Accessibility", NSMakeRect(16, 98, 110, 18), 12, NSFontWeightSemibold, [NSColor secondaryLabelColor])];
    self.permissionValue = AAFLabel(@"Not enabled", NSMakeRect(118, 98, 100, 18), 13, NSFontWeightBold, [NSColor systemOrangeColor]);
    self.permissionValue.alignment = NSTextAlignmentRight;
    [panel addSubview:self.permissionValue];

    self.permissionNotice = AAFLabel(@"",
                                     NSMakeRect(16, 52, 216, 36),
                                     12,
                                     NSFontWeightRegular,
                                     [NSColor secondaryLabelColor]);
    [panel addSubview:self.permissionNotice];

    NSButton *settingsButton = [NSButton buttonWithTitle:@"Open Settings" target:self action:@selector(openSettingsTapped:)];
    settingsButton.frame = NSMakeRect(16, 16, 124, 30);
    settingsButton.bezelStyle = NSBezelStyleRounded;
    [panel addSubview:settingsButton];
}

- (void)buildActivityPanel:(NSView *)panel {
    [panel addSubview:AAFLabel(@"Activity", NSMakeRect(16, 242, 160, 22), 17, NSFontWeightSemibold, [NSColor labelColor])];

    NSScrollView *scroll = [[NSScrollView alloc] initWithFrame:NSMakeRect(16, 16, 760, 216)];
    scroll.hasVerticalScroller = YES;
    scroll.borderType = NSBezelBorder;

    self.logTextView = [[NSTextView alloc] initWithFrame:NSMakeRect(0, 0, 760, 216)];
    self.logTextView.editable = NO;
    self.logTextView.selectable = YES;
    self.logTextView.font = [NSFont monospacedSystemFontOfSize:12 weight:NSFontWeightRegular];
    self.logTextView.textColor = [NSColor secondaryLabelColor];
    self.logTextView.backgroundColor = [NSColor textBackgroundColor];
    self.logTextView.string = @"No activity yet.";

    scroll.documentView = self.logTextView;
    [panel addSubview:scroll];
}

- (BOOL)parseIntegerField:(NSTextField *)field value:(NSInteger *)value message:(NSString **)message {
    NSScanner *scanner = [NSScanner scannerWithString:field.stringValue];
    NSInteger parsed = 0;
    if (![scanner scanInteger:&parsed] || !scanner.isAtEnd) {
        *message = @"Interval and jitter must be whole numbers.";
        return NO;
    }
    *value = parsed;
    return YES;
}

- (BOOL)readInterval:(NSInteger *)interval jitter:(NSInteger *)jitter action:(AAFAction *)action requireFocus:(BOOL *)requireFocus message:(NSString **)message {
    NSInteger parsedInterval = 0;
    NSInteger parsedJitter = 0;

    if (![self parseIntegerField:self.intervalField value:&parsedInterval message:message] ||
        ![self parseIntegerField:self.jitterField value:&parsedJitter message:message]) {
        return NO;
    }

    if (parsedInterval < 10 || parsedInterval > 900) {
        *message = @"Interval must be between 10 and 900 seconds.";
        return NO;
    }

    if (parsedJitter < 0 || parsedJitter > 300) {
        *message = @"Jitter must be between 0 and 300 seconds.";
        return NO;
    }

    parsedJitter = MIN(parsedJitter, MAX(0, parsedInterval - 5));
    self.jitterField.stringValue = [NSString stringWithFormat:@"%ld", (long)parsedJitter];

    *interval = parsedInterval;
    *jitter = parsedJitter;
    *action = (AAFAction)MAX(0, self.actionPopup.indexOfSelectedItem);
    *requireFocus = self.focusGuardButton.state == NSControlStateValueOn;
    return YES;
}

- (void)refreshStatus {
    BOOL running = self.engine.running;
    self.statusPill.stringValue = running ? @"Running" : @"Stopped";
    self.statusPill.textColor = running ? [NSColor systemGreenColor] : [NSColor secondaryLabelColor];
    NSColor *pillColor = running
        ? [[NSColor systemGreenColor] colorWithAlphaComponent:0.12]
        : [NSColor controlBackgroundColor];
    self.statusPill.layer.backgroundColor = [pillColor CGColor];

    self.startButton.enabled = !running;
    self.stopButton.enabled = running;

    if (running && self.engine.nextActionDate != nil) {
        NSInteger seconds = MAX(0, (NSInteger)llround([self.engine.nextActionDate timeIntervalSinceNow]));
        self.nextActionValue.stringValue = AAFSecondsLabel(seconds);
    } else {
        self.nextActionValue.stringValue = @"-";
    }

    self.actionCountValue.stringValue = [NSString stringWithFormat:@"%ld", (long)self.engine.actionCount];

    BOOL trusted = [self.engine isAccessibilityTrusted];
    self.permissionValue.stringValue = trusted ? @"Enabled" : @"Not enabled";
    self.permissionValue.textColor = trusted ? [NSColor systemGreenColor] : [NSColor systemOrangeColor];
    self.permissionNotice.stringValue = trusted
        ? @"Ready to send input."
        : @"Enable Accessibility access for this app before starting.";

    NSArray<NSDictionary<NSString *, NSString *> *> *events = self.engine.events;
    if (events.count == 0) {
        self.logTextView.string = @"No activity yet.";
        return;
    }

    NSMutableArray<NSString *> *lines = [NSMutableArray arrayWithCapacity:events.count];
    for (NSDictionary<NSString *, NSString *> *event in events) {
        [lines addObject:[NSString stringWithFormat:@"%@  %@", event[@"time"], event[@"message"]]];
    }
    self.logTextView.string = [lines componentsJoinedByString:@"\n"];
}

- (void)showError:(NSString *)message {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"Could not start";
    alert.informativeText = message;
    alert.alertStyle = NSAlertStyleWarning;
    if (self.view.window != nil) {
        [alert beginSheetModalForWindow:self.view.window completionHandler:nil];
    } else {
        [alert runModal];
    }
}

- (void)actionChanged:(id)sender {
    AAFAction action = (AAFAction)MAX(0, self.actionPopup.indexOfSelectedItem);
    self.actionDetailLabel.stringValue = AAFActionDetail(action);
}

- (void)startTapped:(id)sender {
    if (![self.engine isAccessibilityTrusted]) {
        [self showError:@"Enable Accessibility access for Roblox Anti-AFK, then press Start again."];
        return;
    }

    NSInteger interval = 0;
    NSInteger jitter = 0;
    AAFAction action = AAFActionSpace;
    BOOL requireFocus = YES;
    NSString *message = nil;
    if (![self readInterval:&interval jitter:&jitter action:&action requireFocus:&requireFocus message:&message]) {
        [self showError:message ?: @"Check the settings and try again."];
        return;
    }

    [self.engine startWithInterval:interval jitter:jitter action:action requireFocus:requireFocus];
    [self refreshStatus];
}

- (void)stopTapped:(id)sender {
    [self.engine stop];
    [self refreshStatus];
}

- (void)openSettingsTapped:(id)sender {
    [self.engine openAccessibilitySettings];
}

@end

@interface AppDelegate : NSObject <NSApplicationDelegate>
@property(nonatomic, strong) NSWindow *window;
@end

@implementation AppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
    [self buildMenu];

    MainViewController *viewController = [[MainViewController alloc] init];
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 840, 640)
                                             styleMask:(NSWindowStyleMaskTitled |
                                                        NSWindowStyleMaskClosable |
                                                        NSWindowStyleMaskMiniaturizable)
                                               backing:NSBackingStoreBuffered
                                                 defer:NO];
    self.window.title = @"Roblox Anti-AFK";
    self.window.contentViewController = viewController;
    [self.window center];
    [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender {
    return YES;
}

- (void)buildMenu {
    NSMenu *menubar = [[NSMenu alloc] init];
    NSMenuItem *appMenuItem = [[NSMenuItem alloc] init];
    [menubar addItem:appMenuItem];
    [NSApp setMainMenu:menubar];

    NSMenu *appMenu = [[NSMenu alloc] init];
    NSString *quitTitle = @"Quit Roblox Anti-AFK";
    NSMenuItem *quitItem = [[NSMenuItem alloc] initWithTitle:quitTitle action:@selector(terminate:) keyEquivalent:@"q"];
    [appMenu addItem:quitItem];
    appMenuItem.submenu = appMenu;
}

@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSApplication *app = [NSApplication sharedApplication];
        AppDelegate *delegate = [[AppDelegate alloc] init];
        app.delegate = delegate;
        [app run];
    }
    return 0;
}
