/**
 * kit/person — a pessoa NA FRENTE do elemento.
 *
 * O elemento (texto, imagem, 3D) vai entre o vídeo-base e o recorte da pessoa;
 * como o recorte redesenha a pessoa por cima, o elemento fica atrás dela.
 * É a mesma técnica do `behind[]` do template (ProRes 4444 / alpha de
 * helpers/person_matte.py), só que para cenas escritas à mão.
 *
 *   <InFrontOfPerson matte="pessoa-3.mov" from={12.4} to={17}>
 *     <MinhaPalavraGigante />
 *   </InFrontOfPerson>
 *
 * `from` é o segundo em que o recorte COMEÇA: o frame 0 do arquivo = `from`
 * (um arquivo por janela, `person_matte.py --start <from> --duration <to-from>`).
 * O recorte passa pela mesma câmera dinâmica do vídeo-base, então fica alinhado.
 */
import React from 'react';
import {Sequence, useVideoConfig} from 'remotion';
import {DynamicVideo} from '../Main';

export const InFrontOfPerson: React.FC<{matte: string; from: number; to: number; children: React.ReactNode}> = ({matte, from, to, children}) => {
  const {fps} = useVideoConfig();
  const a = Math.round(from * fps);
  const dur = Math.max(1, Math.round((to - from) * fps));
  return (
    <Sequence from={a} durationInFrames={dur} layout="none">
      {children}
      <DynamicVideo src={matte} frameOffset={a} transparent />
    </Sequence>
  );
};
