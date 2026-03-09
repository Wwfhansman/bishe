import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../core/providers/app_state_provider.dart';

class VoiceView extends StatefulWidget {
  const VoiceView({super.key});

  @override
  State<VoiceView> createState() => _VoiceViewState();
}

class _VoiceViewState extends State<VoiceView> with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
       vsync: this, 
       duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppStateProvider>();
    final bool isActive = state.connectionState == VoiceConnectionState.connected;
    
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFFF6F8FD),
      ),
      child: SafeArea(
        child: Column(
          children: [
            const Padding(
              padding: EdgeInsets.only(top: 24, left: 24),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('厨房助手 AI', style: TextStyle(color: Colors.black38, fontSize: 14)),
                    SizedBox(height: 4),
                    Text('您好，大厨', style: TextStyle(color: Colors.black87, fontSize: 28, fontWeight: FontWeight.bold)),
                  ],
                ),
              ),
            ),
            
            Expanded(
              child: Center(
                child: GestureDetector(
                  onTap: () async {
                    if (isActive) {
                      await context.read<AppStateProvider>().stopVoiceChat();
                    } else {
                      await context.read<AppStateProvider>().startVoiceChat();
                    }
                  },
                  child: AnimatedBuilder(
                    animation: _pulseController,
                    builder: (context, child) {
                      return Stack(
                        alignment: Alignment.center,
                        children: [
                          if (isActive) ...[
                            // Outer ripple 1
                            Container(
                              width: 250 + (_pulseController.value * 60),
                              height: 250 + (_pulseController.value * 60),
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: Colors.blueAccent.withValues(alpha: 0.05),
                              ),
                            ),
                            // Outer ripple 2
                            Container(
                              width: 180 + (_pulseController.value * 40),
                              height: 180 + (_pulseController.value * 40),
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: Colors.blueAccent.withValues(alpha: 0.1),
                              ),
                            ),
                          ],
                          
                          // Main Button
                          Container(
                            width: 140,
                            height: 140,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              gradient: LinearGradient(
                                colors: isActive 
                                  ? [Colors.blue, const Color(0xFF1565C0)]
                                  : [Colors.grey.shade300, Colors.grey.shade400],
                                begin: Alignment.topLeft,
                                end: Alignment.bottomRight,
                              ),
                              boxShadow: [
                                BoxShadow(
                                  color: (isActive ? Colors.blueAccent : Colors.grey).withValues(alpha: 0.3),
                                  blurRadius: 20,
                                  offset: const Offset(0, 10),
                                )
                              ],
                            ),
                            child: Icon(
                              isActive ? Icons.mic : Icons.mic_off,
                              color: Colors.white,
                              size: 48,
                            ),
                          ),
                        ],
                      );
                    },
                  ),
                ),
              ),
            ),
            
            // Interaction Status & Subtitles
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
              child: Column(
                children: [
                  Text(
                    isActive ? "点击停止" : "点击说话",
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.black87),
                  ),
                  const SizedBox(height: 16),
                  
                  // ASR Text (User Speech)
                  if (state.asrText.isNotEmpty)
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: Colors.blueAccent.withValues(alpha: 0.2)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.person, size: 20, color: Colors.blueAccent),
                          const SizedBox(width: 8),
                          Expanded(child: Text(state.asrText, style: const TextStyle(fontSize: 15))),
                        ],
                      ),
                    ),
                    
                  const SizedBox(height: 12),
                  
                  // LLM Text (AI Response)
                  if (state.llmText.isNotEmpty)
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.blueAccent.withValues(alpha: 0.05),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(Icons.smart_toy, size: 20, color: Colors.blueAccent),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              state.llmText,
                              style: const TextStyle(fontSize: 15, height: 1.4, color: Colors.black87),
                            ),
                          ),
                        ],
                      ),
                    ),
                    
                  if (isActive && state.isAIPlayback)
                    Padding(
                      padding: const EdgeInsets.only(top: 16),
                      child: TextButton.icon(
                        onPressed: () {
                          context.read<AppStateProvider>().interruptAI();
                        },
                        icon: const Icon(Icons.stop_circle_outlined, color: Colors.redAccent),
                        label: const Text('打断 AI 说话', style: TextStyle(color: Colors.redAccent)),
                        style: TextButton.styleFrom(
                          backgroundColor: Colors.redAccent.withValues(alpha: 0.1),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
